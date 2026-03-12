"""Batch workflow scheduler for large-scale structure calculations."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .constants import (
    BATCH_PID_FILE,
    BATCH_LOG_FILE,
    BATCH_STATE_FILE,
    BATCH_STAGES,
    MAX_RETRY_COUNT,
    MONITOR_STATE_FILE,
)
from .contexts import BatchContext
from .exceptions import AbortException
from .path_resolver import BatchPathResolver
from .record_utils import (
    ErrorTask,
    OlpTask,
    _read_jsonl,
    append_error_task,
    append_olp_task,
    count_tasks,
    get_task_retry_count,
    write_olp_tasks,
)
from .template_generator import generate_submit_script
from .utils import ensure_directory, get_logger, load_yaml_config
from .workflow_base import WorkflowBase

if TYPE_CHECKING:
    pass


class BatchScheduler(WorkflowBase):
    """Manages batch iterative computation with dynamic SLURM configuration."""

    def __init__(self, ctx: BatchContext):
        super().__init__()
        self.ctx = ctx
        self.logger = get_logger("batch_scheduler")
        self.state: Dict[str, Any] = self._load_or_init_state()
        self.config = load_yaml_config(self.ctx.config_path)

        if self.ctx.monitor is not None:
            self.monitor = self.ctx.monitor
        else:
            self._init_monitor(
                monitor_state_file=self.ctx.workflow_root / MONITOR_STATE_FILE
            )

    def _load_or_init_state(self) -> Dict[str, Any]:
        """Load existing state or initialize new state."""
        if self.ctx.state_file is None:
            self.ctx.state_file = self.ctx.workflow_root / BATCH_STATE_FILE

        if self.ctx.resume and self.ctx.state_file.exists():
            with open(self.ctx.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                self.logger.info("Resumed from state: %s", self.ctx.state_file)
                return state

        state = {
            "current_batch": 0,
            "current_stage": "olp",
            "completed_batches": [],
            "initialized": False,
            "total_batches": 0,
        }
        self._save_state(state)
        return state

    def _save_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        """Save current state to file."""
        if state is None:
            state = self.state
        if self.ctx.state_file is None:
            return
        ensure_directory(self.ctx.state_file.parent)
        state["last_update"] = datetime.now().isoformat()
        with open(self.ctx.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _get_path_resolver(self, batch_index: int) -> BatchPathResolver:
        """Get PathResolver for a specific batch."""
        return BatchPathResolver(self.ctx.workflow_root, batch_index)

    def _init_batch_tasks(self) -> int:
        """
        Initialize batch task files from root todo_list.json.

        Divides tasks by batch_size and writes to each batch's olp_tasks.jsonl.

        Returns:
            Number of batches created
        """
        resolver = self._get_path_resolver(0)
        todo_file = resolver.get_todo_list_file()

        if not todo_file.exists():
            self.logger.warning("todo_list.json not found at %s", todo_file)
            return 0

        tasks = list(_read_jsonl(todo_file))
        if not tasks:
            self.logger.warning("No tasks in todo_list.json")
            return 0

        batch_size = self.ctx.batch_size
        num_batches = math.ceil(len(tasks) / batch_size)

        self.logger.info(
            "Initializing %d batches for %d tasks (batch_size=%d)",
            num_batches,
            len(tasks),
            batch_size,
        )

        for i in range(num_batches):
            start = i * batch_size
            end = min(start + batch_size, len(tasks))
            batch_tasks = tasks[start:end]

            batch_resolver = self._get_path_resolver(i)
            tasks_file = batch_resolver.get_olp_tasks_file()
            tasks_file.parent.mkdir(parents=True, exist_ok=True)

            olp_tasks = [OlpTask(path=t["path"]) for t in batch_tasks]
            write_olp_tasks(tasks_file, olp_tasks)

            self.logger.info("Created batch %d with %d tasks", i, len(batch_tasks))

        return num_batches

    def _count_batch_tasks(self, resolver: BatchPathResolver) -> int:
        """Count tasks in current batch."""
        return count_tasks(resolver.get_olp_tasks_file())

    def _collect_failed_tasks(self, resolver: BatchPathResolver) -> List[OlpTask]:
        """
        Collect failed tasks from all stages.

        Filters out tasks that exceeded max retry count.

        Args:
            resolver: Current batch path resolver

        Returns:
            List of failed tasks that can be retried
        """
        failed_paths = set()

        for stage in BATCH_STAGES:
            error_file = getattr(resolver, f"get_{stage}_error_file")()
            if error_file.exists():
                for d in _read_jsonl(error_file):
                    path = d.get("path", "")
                    if path:
                        failed_paths.add(path)

        if not failed_paths:
            return []

        valid_tasks = []
        permanent_errors = []

        for path in failed_paths:
            retry_count = get_task_retry_count(self.ctx.workflow_root, path)
            if retry_count >= MAX_RETRY_COUNT:
                permanent_errors.append(
                    ErrorTask(
                        path=path,
                        stage="exceeded",
                        error=f"Max retry count ({MAX_RETRY_COUNT}) exceeded",
                        batch_id=str(resolver.batch_index),
                        task_id="",
                        retry_count=retry_count,
                    )
                )
            else:
                valid_tasks.append(OlpTask(path=path))

        if permanent_errors:
            perm_file = resolver.get_permanent_error_file()
            perm_file.parent.mkdir(parents=True, exist_ok=True)
            for task in permanent_errors:
                append_error_task(perm_file, task)
            self.logger.warning(
                "%d tasks exceeded max retries, saved to %s",
                len(permanent_errors),
                perm_file,
            )

        self.logger.info(
            "Collected %d failed tasks (%d permanent failures)",
            len(valid_tasks),
            len(permanent_errors),
        )

        return valid_tasks

    def _forward_failed_tasks(
        self, failed_tasks: List[OlpTask], next_resolver: BatchPathResolver
    ) -> None:
        """
        Forward failed tasks to next batch.

        Args:
            failed_tasks: List of failed tasks to retry
            next_resolver: Path resolver for next batch
        """
        if not failed_tasks:
            return

        tasks_file = next_resolver.get_olp_tasks_file()
        tasks_file.parent.mkdir(parents=True, exist_ok=True)

        for task in failed_tasks:
            append_olp_task(tasks_file, task)

        self.logger.info(
            "Forwarded %d failed tasks to batch %d",
            len(failed_tasks),
            next_resolver.batch_index,
        )

    def _get_python_path(self, stage: str = "olp") -> str:
        """Get Python interpreter path for stage."""
        software_config = self.config.get("software", {})
        if stage == "infer":
            path = software_config.get("python_deeph", "python")
            if path.endswith("/"):
                return path + "python"
            return path
        return software_config.get("python", "python")

    def _submit_slurm_job(
        self, script_path: Path, work_dir: Path, job_name: str
    ) -> str:
        """
        Submit SLURM job and return job ID.

        Args:
            script_path: Path to submit.sh
            work_dir: Working directory
            job_name: Job name for logging

        Returns:
            Job ID string
        """
        result = subprocess.run(
            "sbatch submit.sh",
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(work_dir),
        )

        if result.returncode != 0:
            self.logger.error("sbatch failed: %s", result.stderr)
            raise RuntimeError(f"sbatch failed: {result.stderr}")

        output = result.stdout.strip()
        if "Submitted batch job" in output:
            job_id = output.split()[-1]
            self.logger.info("Submitted %s job: %s", job_name, job_id)
            return job_id

        self.logger.warning("Unexpected sbatch output: %s", output)
        return ""

    def _check_slurm_job_state(self, job_id: str) -> str:
        """Check SLURM job state."""
        if not job_id:
            return "UNKNOWN"

        main_job_id = job_id.split("_")[0]
        result = subprocess.run(
            f"sacct -j {main_job_id} --format=State --noheader --parsertype",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return "UNKNOWN"

        states = [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
        return states[0] if states else "UNKNOWN"

    def _wait_for_job_completion(
        self, job_id: str, stage: str, check_interval: int = 60
    ) -> bool:
        """
        Wait for SLURM job to complete.

        Args:
            job_id: SLURM job ID
            stage: Stage name for logging
            check_interval: Check interval in seconds

        Returns:
            True if completed successfully, False if failed
        """
        terminal_states = {
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "TIMEOUT",
            "NODE_FAIL",
            "OUT_OF_MEMORY",
        }

        while True:
            state = self._check_slurm_job_state(job_id)
            self.logger.info("[%s] Job %s state: %s", stage, job_id, state)

            if state in terminal_states:
                if state == "COMPLETED":
                    return True
                else:
                    self.logger.error(
                        "[%s] Job %s failed with state: %s", stage, job_id, state
                    )
                    return False

            time.sleep(check_interval)

    def _run_stage(
        self, stage: str, resolver: BatchPathResolver, num_tasks: int
    ) -> bool:
        """
        Run a single stage.

        Args:
            stage: Stage name (olp, infer, calc)
            resolver: Path resolver
            num_tasks: Number of tasks

        Returns:
            True if stage completed successfully
        """
        stage_config_map = {"olp": "0olp", "infer": "1infer", "calc": "2calc"}
        config_key = stage_config_map[stage]

        stage_dir = getattr(resolver, f"get_{stage}_slurm_dir")()
        stage_dir.mkdir(parents=True, exist_ok=True)

        tasks_file = None
        if stage == "olp":
            tasks_file = str(resolver.get_olp_tasks_file())
        elif stage == "calc":
            tasks_file = str(resolver.get_calc_tasks_file())

        workdir = str(resolver.get_workdir())

        script_path = generate_submit_script(
            stage_name=config_key,
            stage_dir=stage_dir,
            stage_config=self.config.get(config_key, {}),
            python_path=self._get_python_path(stage),
            config_path=str(self.ctx.config_path),
            software_config=self.config.get("software", {}),
            num_tasks=num_tasks,
            tasks_file=tasks_file,
            workdir=workdir,
            batch_index=resolver.batch_index,
            workflow_root=str(resolver._workflow_root),
        )

        job_id = self._submit_slurm_job(script_path, stage_dir, f"batch-{stage}")

        if not job_id:
            return False

        return self._wait_for_job_completion(job_id, stage)

    def _has_pending_batches(self) -> bool:
        """Check if there are pending batches to process."""
        resolver = self._get_path_resolver(self.state["current_batch"])
        return self._count_batch_tasks(resolver) > 0

    def _write_pid(self) -> None:
        """Write PID file."""
        pid_file = self.ctx.workflow_root / BATCH_PID_FILE
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self) -> None:
        """Remove PID file."""
        pid_file = self.ctx.workflow_root / BATCH_PID_FILE
        if pid_file.exists():
            pid_file.unlink()

    def _is_running(self) -> bool:
        """Check if another instance is running."""
        pid_file = self.ctx.workflow_root / BATCH_PID_FILE
        if not pid_file.exists():
            return False
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            return False

    def run(self) -> Dict[str, Any]:
        """
        Run the batch workflow loop.

        Returns:
            Result dict with status and batch count
        """
        if self._is_running():
            print("已有批量工作流实例运行中，请先使用 dlazy batch-stop 停止")
            return {"status": "already_running"}

        self.logger.info(
            "Starting batch workflow with batch_size=%d", self.ctx.batch_size
        )
        print(f"批量工作流已启动 (PID: {os.getpid()})")

        def signal_handler(signum, frame):
            self.logger.info("收到停止信号，正在退出...")
            self._remove_pid()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        self._write_pid()

        try:
            if not self.state.get("initialized"):
                num_batches = self._init_batch_tasks()
                self.state["initialized"] = True
                self.state["total_batches"] = num_batches
                self._save_state()

            while self._has_pending_batches():
                if self._check_abort():
                    raise AbortException(
                        self._get_abort_reason() or "Max retries exceeded"
                    )

                batch_index = self.state["current_batch"]
                resolver = self._get_path_resolver(batch_index)

                num_tasks = self._count_batch_tasks(resolver)
                if num_tasks == 0:
                    self.logger.info("Batch %d empty, skipping", batch_index)
                    self.state["current_batch"] = batch_index + 1
                    self._save_state()
                    continue

                self.logger.info(
                    "Processing batch %d: %d tasks", batch_index, num_tasks
                )

                ensure_directory(resolver.get_workdir())

                for stage in BATCH_STAGES:
                    stage_key = f"{stage}_completed"
                    if not self.state.get(stage_key):
                        success = self._run_stage(stage, resolver, num_tasks)
                        if not success:
                            self.logger.error(
                                "Batch %d stage %s failed", batch_index, stage
                            )
                        self.state[stage_key] = True
                        self._save_state()
                        self._save_monitor_state(
                            self.ctx.workflow_root / MONITOR_STATE_FILE
                        )

                    if self._check_abort():
                        raise AbortException(
                            self._get_abort_reason() or "Max retries exceeded"
                        )

                failed_tasks = self._collect_failed_tasks(resolver)
                if failed_tasks:
                    next_resolver = resolver.get_next_batch_resolver()
                    self._forward_failed_tasks(failed_tasks, next_resolver)

                self.state["completed_batches"].append(batch_index)
                self.state["current_batch"] = batch_index + 1
                for stage in BATCH_STAGES:
                    self.state[f"{stage}_completed"] = False
                self._save_state()
                self._save_monitor_state(self.ctx.workflow_root / MONITOR_STATE_FILE)

            self.logger.info("Batch workflow completed")
            return {
                "status": "completed",
                "batches": len(self.state["completed_batches"]),
            }

        except AbortException as e:
            self.logger.error("Batch workflow aborted: %s", e.reason)
            self._save_state()
            self._save_monitor_state(self.ctx.workflow_root / MONITOR_STATE_FILE)
            return {
                "status": "aborted",
                "reason": e.reason,
                "batches": len(self.state["completed_batches"]),
            }
        finally:
            self._remove_pid()

    def show_status(self) -> None:
        """Show batch workflow status."""
        print("=== 批量工作流状态 ===")

        pid_file = self.ctx.workflow_root / BATCH_PID_FILE
        if not pid_file.exists():
            print("进程状态: 未运行\n")
        else:
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                print(f"进程状态: 运行中 (PID: {pid})\n")
            except (ValueError, OSError):
                print("进程状态: 已停止\n")

        state_file = self.ctx.workflow_root / BATCH_STATE_FILE
        if not state_file.exists():
            print("批量工作流未启动或状态文件不存在")
            return

        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        print(f"初始化: {'是' if state.get('initialized') else '否'}")
        print(f"当前批次: {state.get('current_batch', 0)}")
        print(f"总批次数: {state.get('total_batches', 'N/A')}")
        print(f"已完成批次: {len(state.get('completed_batches', []))}")

        for stage in BATCH_STAGES:
            stage_key = f"{stage}_completed"
            status = "✓ 完成" if state.get(stage_key) else "待执行"
            print(f"  {stage}: {status}")

        if state.get("last_update"):
            print(f"\n最后更新: {state.get('last_update')}")

        monitor_file = self.ctx.workflow_root / MONITOR_STATE_FILE
        if monitor_file.exists():
            with open(monitor_file, "r", encoding="utf-8") as f:
                monitor_state = json.load(f)

            errors = monitor_state.get("errors", [])
            if errors:
                print(f"\n错误记录: {len(errors)} 条")
                for err in errors[-5:]:
                    print(
                        f"  - [{err.get('stage')}] {err.get('failure_type')}: {err.get('message')}"
                    )

            if monitor_state.get("abort_flag"):
                print(f"\n中断原因: {monitor_state.get('abort_reason', '未知')}")

    def stop(self) -> None:
        """Stop the running batch workflow."""
        pid_file = self.ctx.workflow_root / BATCH_PID_FILE
        if not pid_file.exists():
            print("没有运行中的批量工作流实例")
            return

        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"已发送停止信号到进程 {pid}")
        except (ValueError, OSError) as e:
            print(f"停止失败: {e}")


class BatchWorkflowManager(BatchScheduler):
    """Legacy alias for BatchScheduler."""

    pass
