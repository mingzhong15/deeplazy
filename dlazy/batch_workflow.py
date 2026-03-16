"""Batch workflow scheduler for large-scale structure calculations."""

from __future__ import annotations

import json
import math
import os
import shutil
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
from .core.exceptions import AbortException
from dlazy.scheduler import SlurmScheduler, JobManager, SubmitConfig
from dlazy.state import TaskStateStore, CheckpointManager
from .core import (
    ErrorTask,
    OlpTask,
    append_error_task,
    append_olp_task,
    count_tasks,
    get_task_retry_count,
    write_olp_tasks,
)
from .core.tasks import _read_jsonl
from .utils.concurrency import atomic_write_json, FileLock
from .path_resolver import BatchPathResolver
from .template_generator import generate_submit_script
from .utils import (
    ensure_directory,
    get_existing_batch_count,
    get_logger,
    get_next_backup_index,
    load_yaml_config,
)
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

        # Initialize new scheduler components (lazy initialization)
        self._new_scheduler: Optional[SlurmScheduler] = None
        self._job_manager: Optional[JobManager] = None
        self._task_store: Optional[TaskStateStore] = None
        self._checkpoint_manager: Optional[CheckpointManager] = None

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

        # --fresh: 删除已有状态，从头开始
        if self.ctx.fresh and self.ctx.state_file.exists():
            self.ctx.state_file.unlink()
            self.logger.info("Fresh start: removed existing state file")

        # 自动加载已有状态
        if self.ctx.state_file.exists():
            with FileLock(self.ctx.state_file, timeout=30.0):
                with open(self.ctx.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.logger.info("Resumed from state: %s", self.ctx.state_file)
                return state

        # 初始化新状态 - 检测现有batch目录
        start_batch = get_existing_batch_count(self.ctx.workflow_root)
        if start_batch > 0:
            self.logger.info(
                "Detected %d existing batches, starting from batch %d",
                start_batch,
                start_batch,
            )

        # 计算原始任务数
        original_task_count = 0
        origin_file = self.ctx.workflow_root / "todo_list.origin"
        todo_file = self.ctx.workflow_root / "todo_list.json"

        if origin_file.exists():
            original_task_count = sum(1 for _ in open(origin_file, "r"))
        elif todo_file.exists():
            original_task_count = sum(1 for _ in open(todo_file, "r"))

        state = {
            "current_batch": start_batch,
            "current_stage": "olp",
            "completed_batches": [],
            "initialized": False,
            "total_batches": 0,
            "start_batch_index": start_batch,
            "original_task_count": original_task_count,
            "batch_size": self.ctx.batch_size,
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

        if "batch_times" not in state:
            state["batch_times"] = {}

        batch_idx = state.get("current_batch", 0)
        batch_key = str(batch_idx)
        if batch_key not in state["batch_times"]:
            state["batch_times"][batch_key] = {"start": datetime.now().isoformat()}

        # 使用原子写入，加锁保护
        with FileLock(self.ctx.state_file, timeout=30.0):
            atomic_write_json(self.ctx.state_file, state)

    def _get_path_resolver(self, batch_index: int) -> BatchPathResolver:
        """Get PathResolver for a specific batch."""
        return BatchPathResolver(self.ctx.workflow_root, batch_index)

    def _init_batch_tasks(self, start_batch_index: int = 0) -> int:
        """
        Initialize batch task files from root todo_list.json.

        Divides tasks by batch_size and writes to each batch's olp_tasks.jsonl.

        Args:
            start_batch_index: Starting batch index (default 0, for resume/append mode)

        Returns:
            Number of batches created
        """
        resolver = self._get_path_resolver(0)
        todo_file = resolver.get_todo_list_file()

        if not todo_file.exists():
            self.logger.warning("todo_list.json not found at %s", todo_file)
            return 0

        # 首次运行时，备份原始文件
        if start_batch_index == 0:
            origin_file = self.ctx.workflow_root / "todo_list.origin"
            if not origin_file.exists():
                shutil.copy(todo_file, origin_file)
                self.logger.info("备份原始任务列表到: %s", origin_file)

        tasks = list(_read_jsonl(todo_file))
        if not tasks:
            self.logger.warning("No tasks in todo_list.json")
            return 0

        batch_size = self.ctx.batch_size
        num_batches = math.ceil(len(tasks) / batch_size)

        self.logger.info(
            "Initializing %d batches for %d tasks (batch_size=%d), starting from batch %d",
            num_batches,
            len(tasks),
            batch_size,
            start_batch_index,
        )

        for i in range(num_batches):
            batch_index = start_batch_index + i
            start = i * batch_size
            end = min(start + batch_size, len(tasks))
            batch_tasks = tasks[start:end]

            batch_resolver = self._get_path_resolver(batch_index)
            tasks_file = batch_resolver.get_olp_tasks_file()
            tasks_file.parent.mkdir(parents=True, exist_ok=True)

            olp_tasks = [OlpTask(path=t["path"]) for t in batch_tasks]
            write_olp_tasks(tasks_file, olp_tasks)

            self.logger.info(
                "Created batch %d with %d tasks", batch_index, len(batch_tasks)
            )

        return num_batches

    def _init_single_batch(self, batch_index: int) -> int:
        """Initialize a single batch's task file (lazy creation).

        Args:
            batch_index: Index of batch to create

        Returns:
            Number of tasks in this batch (0 if no more tasks)
        """
        resolver = self._get_path_resolver(0)
        todo_file = resolver.get_todo_list_file()

        if not todo_file.exists():
            return 0

        tasks = list(_read_jsonl(todo_file))
        if not tasks:
            return 0

        batch_size = self.ctx.batch_size
        start = batch_index * batch_size

        if start >= len(tasks):
            return 0

        end = min(start + batch_size, len(tasks))
        batch_tasks = tasks[start:end]

        batch_resolver = self._get_path_resolver(batch_index)
        tasks_file = batch_resolver.get_olp_tasks_file()
        tasks_file.parent.mkdir(parents=True, exist_ok=True)

        olp_tasks = [OlpTask(path=t["path"]) for t in batch_tasks]
        write_olp_tasks(tasks_file, olp_tasks)

        self.logger.info(
            "Created batch %d with %d tasks (lazy creation)",
            batch_index,
            len(batch_tasks),
        )
        return len(batch_tasks)

    def _count_batch_tasks(self, resolver: BatchPathResolver) -> int:
        """Count tasks in current batch."""
        return count_tasks(resolver.get_olp_tasks_file())

    def _collect_failed_tasks(
        self,
        resolver: BatchPathResolver,
    ) -> List[OlpTask]:
        """
        Collect failed tasks based on output file detection.

        Detects failure by comparing input tasks with actual outputs at each stage.
        Writes error_tasks.jsonl for record keeping.

        Args:
            resolver: Current batch path resolver

        Returns:
            List of failed tasks that can be retried
        """
        from .constants import (
            OVERLAP_FILENAME,
            HAMILTONIAN_FILENAME,
            SLURM_SUBDIR_TEMPLATE,
            OUTPUT_SUBDIR_TEMPLATE,
            TASK_DIR_PREFIX,
            ERROR_TASKS_FILE,
        )

        # 1. 获取所有输入任务路径
        all_paths = {}  # path -> (index, task_dict) mapping
        olp_tasks_file = resolver.get_olp_tasks_file()
        for i, task in enumerate(_read_jsonl(olp_tasks_file)):
            all_paths[task["path"]] = (i, task)

        if not all_paths:
            return []

        # 2. 检查 OLP 阶段成功情况
        olp_success_paths = set()
        olp_output_dir = resolver.get_olp_output_dir()
        if olp_output_dir.exists():
            for path, (idx, task) in all_paths.items():
                overlap_file = (
                    olp_output_dir / f"{TASK_DIR_PREFIX}.{idx:06d}" / OVERLAP_FILENAME
                )
                if overlap_file.exists():
                    olp_success_paths.add(path)

        # 3. 检查 Infer 阶段成功情况（从 calc_tasks.jsonl 获取路径）
        infer_success_paths = set()
        calc_tasks_file = resolver.get_calc_tasks_file()
        if calc_tasks_file.exists():
            for task in _read_jsonl(calc_tasks_file):
                path = task.get("path", "")
                geth_path = Path(task.get("geth_path", ""))
                if path and geth_path.exists():
                    ham_file = geth_path / HAMILTONIAN_FILENAME
                    if ham_file.exists():
                        infer_success_paths.add(path)

        # 4. 检查 Calc 阶段成功情况
        calc_success_paths = set()
        calc_output_dir = resolver.get_calc_output_dir()
        if calc_output_dir.exists():
            # 需要建立 calc_tasks index 到 path 的映射
            if calc_tasks_file.exists():
                for i, task in enumerate(_read_jsonl(calc_tasks_file)):
                    path = task.get("path", "")
                    ham_file = (
                        calc_output_dir
                        / f"{TASK_DIR_PREFIX}.{i:06d}"
                        / "geth"
                        / HAMILTONIAN_FILENAME
                    )
                    if ham_file.exists():
                        calc_success_paths.add(path)

        # 5. 统计各阶段失败
        olp_failed = all_paths.keys() - olp_success_paths
        infer_failed = olp_success_paths - infer_success_paths
        calc_failed = infer_success_paths - calc_success_paths

        self.logger.info(
            "Stage statistics: OLP=%d/%d, Infer=%d/%d, Calc=%d/%d",
            len(olp_success_paths),
            len(all_paths),
            len(infer_success_paths),
            len(olp_success_paths) if olp_success_paths else len(all_paths),
            len(calc_success_paths),
            len(infer_success_paths) if infer_success_paths else 0,
        )

        # 6. 收集所有失败路径及其阶段
        failed_with_stage = []
        for path in olp_failed:
            failed_with_stage.append((path, "olp"))
        for path in infer_failed:
            failed_with_stage.append((path, "infer"))
        for path in calc_failed:
            failed_with_stage.append((path, "calc"))

        if not failed_with_stage:
            return []

        # 7. 分类处理：基于 retry_count 判断永久失败
        valid_tasks = []
        permanent_errors = []
        error_tasks = []

        for path, stage in failed_with_stage:
            retry_count = get_task_retry_count(self.ctx.workflow_root, path)
            task_dict = all_paths.get(path, (0, {}))[1]
            current_retry = task_dict.get("retry_count", retry_count)

            if current_retry >= MAX_RETRY_COUNT:
                permanent_errors.append(
                    ErrorTask(
                        path=path,
                        stage=stage,
                        error=f"Exceeded max retry count ({MAX_RETRY_COUNT})",
                        batch_id=str(resolver.batch_index),
                        task_id="",
                        retry_count=current_retry,
                    )
                )
            else:
                valid_tasks.append(
                    OlpTask(
                        path=path,
                        source_batch=task_dict.get("source_batch", -1),
                        retry_count=current_retry,
                    )
                )

            # 记录所有失败到 error_tasks.jsonl
            error_tasks.append(
                ErrorTask(
                    path=path,
                    stage=stage,
                    error="Missing output file",
                    batch_id=str(resolver.batch_index),
                    task_id="",
                    retry_count=current_retry,
                )
            )

        # 8. 写入 error_tasks.jsonl（按阶段选择错误文件）
        if error_tasks:
            for task in error_tasks:
                if task.stage == "olp":
                    error_file = resolver.get_olp_error_file()
                elif task.stage == "infer":
                    error_file = resolver.get_infer_error_file()
                elif task.stage == "calc":
                    error_file = resolver.get_calc_error_file()
                else:
                    error_file = resolver.get_olp_error_file()
                error_file.parent.mkdir(parents=True, exist_ok=True)
                append_error_task(error_file, task)
            self.logger.info(
                "Wrote %d error tasks",
                len(error_tasks),
            )

        # 9. 写入永久失败记录
        if permanent_errors:
            perm_file = resolver.get_permanent_error_file()
            perm_file.parent.mkdir(parents=True, exist_ok=True)
            for task in permanent_errors:
                append_error_task(perm_file, task)
            self.logger.warning(
                "%d tasks marked as permanent failure (retry count exceeded), saved to %s",
                len(permanent_errors),
                perm_file,
            )

        self.logger.info(
            "Collected %d failed tasks (%d permanent failures due to retry limit)",
            len(valid_tasks),
            len(permanent_errors),
        )

        return valid_tasks

    def _forward_failed_tasks(
        self,
        failed_tasks: List[OlpTask],
        next_resolver: BatchPathResolver,
        current_batch_index: int,
    ) -> None:
        """
        Forward failed tasks to next batch.

        Args:
            failed_tasks: List of failed tasks to retry
            next_resolver: Path resolver for next batch
            current_batch_index: Current batch index (for source_batch tracking)
        """
        if not failed_tasks:
            return

        tasks_file = next_resolver.get_olp_tasks_file()
        tasks_file.parent.mkdir(parents=True, exist_ok=True)

        for task in failed_tasks:
            relay_task = OlpTask(
                path=task.path,
                source_batch=current_batch_index,
                retry_count=task.retry_count + 1,
            )
            append_olp_task(tasks_file, relay_task)

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

    def _init_new_scheduler(self) -> None:
        """Initialize new scheduler components if on SLURM."""
        if self._new_scheduler is not None:
            return

        if shutil.which("sbatch"):
            self._new_scheduler = SlurmScheduler(retry_count=3, retry_delay=10.0)
            self._task_store = TaskStateStore()
            self._job_manager = JobManager(
                scheduler=self._new_scheduler,
                state_store=self._task_store,
            )
            self._checkpoint_manager = CheckpointManager(
                checkpoint_dir=self.ctx.workflow_root / "checkpoints"
            )
            self.logger.info("Initialized new scheduler components")

    def _submit_slurm_job_new(
        self, script_path: Path, job_name: str, config: Optional[SubmitConfig] = None
    ) -> str:
        """Submit job using new SlurmScheduler."""
        assert self._new_scheduler is not None
        if config is None:
            config = SubmitConfig(job_name=job_name)
        return self._new_scheduler.submit(script_path, config)

    def _check_slurm_job_state_new(self, job_id: str) -> str:
        """Check job state using new SlurmScheduler."""
        assert self._new_scheduler is not None
        status = self._new_scheduler.check_status(job_id)
        return str(status)

    def _submit_slurm_job(
        self,
        script_path: Path,
        work_dir: Path,
        job_name: str,
        max_retries: int = 3,
        retry_delay: int = 10,
    ) -> str:
        """
        Submit SLURM job with automatic retry on failure.

        Args:
            script_path: Path to submit.sh
            work_dir: Working directory
            job_name: Job name for logging
            max_retries: Maximum number of retry attempts (default: 3)
            retry_delay: Delay in seconds between retries (default: 10)

        Returns:
            Job ID string

        Raises:
            RuntimeError: If all retry attempts fail
        """
        self._init_new_scheduler()
        if self._new_scheduler:
            return self._submit_slurm_job_new(script_path, job_name)

        last_error = ""
        for attempt in range(1, max_retries + 1):
            result = subprocess.run(
                "sbatch submit.sh",
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(work_dir),
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if "Submitted batch job" in output:
                    job_id = output.split()[-1]
                    self.logger.info("Submitted %s job: %s", job_name, job_id)
                    return job_id
                self.logger.warning("Unexpected sbatch output: %s", output)
                return ""

            last_error = result.stderr
            self.logger.warning(
                "sbatch failed (attempt %d/%d): %s",
                attempt,
                max_retries,
                last_error,
            )

            if attempt < max_retries:
                self.logger.info("Retrying in %d seconds...", retry_delay)
                time.sleep(retry_delay)

        raise RuntimeError(f"sbatch failed after {max_retries} attempts: {last_error}")

    def _check_slurm_job_state(self, job_id: str) -> str:
        """Check SLURM job state."""
        if not job_id:
            return "UNKNOWN"

        if self._new_scheduler:
            return self._check_slurm_job_state_new(job_id)

        main_job_id = job_id.split("_")[0]
        result = subprocess.run(
            f"sacct -j {main_job_id} --format=State --noheader",
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

        self.state["current_job_id"] = job_id
        self.state["current_stage"] = stage
        self._save_state()

        success = self._wait_for_job_completion(job_id, stage)

        if success and self._checkpoint_manager:
            output_dir = getattr(resolver, f"get_{stage}_output_dir")()
            self._checkpoint_manager.save_checkpoint(
                task_id=f"batch_{resolver.batch_index}_{stage}",
                output_path=str(output_dir),
                stage=stage,
            )

        return success

    def _has_pending_batches(self) -> bool:
        """Check if there are pending batches to process."""
        resolver = self._get_path_resolver(self.state["current_batch"])
        return self._count_batch_tasks(resolver) > 0

    def _write_pid(self) -> None:
        """Write PID file with lock."""
        pid_file = self.ctx.workflow_root / BATCH_PID_FILE
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(pid_file):
            with open(pid_file, "w") as f:
                f.write(str(os.getpid()))

    def _remove_pid(self) -> None:
        """Remove PID file with lock."""
        pid_file = self.ctx.workflow_root / BATCH_PID_FILE
        if pid_file.exists():
            with FileLock(pid_file):
                if pid_file.exists():
                    pid_file.unlink()

    def _is_running(self) -> bool:
        """Check if another instance is running with lock."""
        pid_file = self.ctx.workflow_root / BATCH_PID_FILE
        if not pid_file.exists():
            return False
        try:
            with FileLock(pid_file, timeout=1.0):
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                return True
        except (ValueError, OSError, TimeoutError):
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

        resolver = self._get_path_resolver(0)
        todo_file = resolver.get_todo_list_file()
        if todo_file.exists():
            tasks = list(_read_jsonl(todo_file))
            self.state["total_tasks"] = len(tasks)
            self.state["estimated_batches"] = math.ceil(
                len(tasks) / self.ctx.batch_size
            )
            self._save_state()

        try:
            while True:
                if self._check_abort():
                    raise AbortException(
                        self._get_abort_reason() or "Max retries exceeded"
                    )

                batch_index = self.state["current_batch"]
                resolver = self._get_path_resolver(batch_index)

                tasks_file = resolver.get_olp_tasks_file()
                if not tasks_file.exists():
                    num_tasks = self._init_single_batch(batch_index)
                    if num_tasks == 0:
                        self.logger.info("No more tasks, workflow complete")
                        break
                else:
                    num_tasks = self._count_batch_tasks(resolver)
                    if num_tasks == 0:
                        self.logger.info(
                            "Batch %d empty, workflow complete", batch_index
                        )
                        break

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
                    self._forward_failed_tasks(failed_tasks, next_resolver, batch_index)

                batch_key = str(batch_index)
                if "batch_times" not in self.state:
                    self.state["batch_times"] = {}
                if batch_key not in self.state["batch_times"]:
                    self.state["batch_times"][batch_key] = {}
                self.state["batch_times"][batch_key]["end"] = datetime.now().isoformat()

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
            with FileLock(pid_file, timeout=5.0):
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"已发送停止信号到进程 {pid}")
        except TimeoutError:
            print("获取锁超时，可能进程正在退出")
        except (ValueError, OSError) as e:
            print(f"停止失败: {e}")

    def extract_retry_tasks(self, output_file: Optional[Path] = None) -> Dict[str, Any]:
        """
        提取未完成的任务列表

        Args:
            output_file: 输出文件路径，默认为 workflow_root / todo_list_retry.json

        Returns:
            {
                'total': 704,
                'completed': 625,
                'failed': 79,
                'stages': {
                    'olp': {'input': 704, 'output': 704, 'failed': 0},
                    'infer': {'input': 704, 'output': 634, 'failed': 70},
                    'calc': {'input': 634, 'output': 503, 'failed': 131}
                },
                'output_file': 'todo_list_retry.json'
            }
        """
        from .constants import (
            OVERLAP_FILENAME,
            HAMILTONIAN_FILENAME,
            BATCH_DIR_PREFIX,
            SLURM_SUBDIR_TEMPLATE,
            OUTPUT_SUBDIR_TEMPLATE,
            TASK_DIR_PREFIX,
            CALC_TASKS_FILE,
            OLP_TASKS_FILE,
        )
        from .core.tasks import read_olp_tasks, read_calc_tasks

        if output_file is None:
            output_file = self.ctx.workflow_root / "todo_list_retry.json"
        else:
            output_file = Path(output_file)

        todo_file = self.ctx.workflow_root / "todo_list.json"
        if not todo_file.exists():
            self.logger.warning("todo_list.json not found at %s", todo_file)
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "stages": {},
                "output_file": str(output_file),
            }

        all_tasks = list(_read_jsonl(todo_file))
        all_paths = {t["path"] for t in all_tasks}
        total_tasks = len(all_paths)

        olp_success_paths = set()
        infer_success_paths = set()
        calc_success_paths = set()

        batch_dirs = sorted(self.ctx.workflow_root.glob(f"{BATCH_DIR_PREFIX}.*"))

        for batch_dir in batch_dirs:
            slurm_olp_dir = batch_dir / SLURM_SUBDIR_TEMPLATE.format("olp")
            olp_tasks_file = slurm_olp_dir / OLP_TASKS_FILE
            olp_output_dir = batch_dir / OUTPUT_SUBDIR_TEMPLATE.format("olp")

            if olp_tasks_file.exists() and olp_output_dir.exists():
                olp_tasks = read_olp_tasks(olp_tasks_file)
                for i, task in enumerate(olp_tasks):
                    task_dir = olp_output_dir / f"{TASK_DIR_PREFIX}.{i:06d}"
                    overlap_file = task_dir / OVERLAP_FILENAME
                    if overlap_file.exists():
                        olp_success_paths.add(task.path)

            slurm_calc_dir = batch_dir / SLURM_SUBDIR_TEMPLATE.format("calc")
            calc_tasks_file = slurm_calc_dir / CALC_TASKS_FILE
            calc_output_dir = batch_dir / OUTPUT_SUBDIR_TEMPLATE.format("calc")

            if calc_tasks_file.exists():
                calc_tasks = read_calc_tasks(calc_tasks_file)
                for i, task in enumerate(calc_tasks):
                    geth_path = Path(task.geth_path)
                    if geth_path.exists():
                        infer_ham_file = geth_path / HAMILTONIAN_FILENAME
                        if infer_ham_file.exists():
                            infer_success_paths.add(task.path)

                    if calc_output_dir.exists():
                        calc_task_dir = calc_output_dir / f"{TASK_DIR_PREFIX}.{i:06d}"
                        calc_ham_file = calc_task_dir / "geth" / HAMILTONIAN_FILENAME
                        if calc_ham_file.exists():
                            calc_success_paths.add(task.path)

        calc_success = calc_success_paths & all_paths
        infer_success = infer_success_paths & all_paths
        olp_success = olp_success_paths & all_paths

        failed_paths = all_paths - calc_success

        retry_tasks = [t for t in all_tasks if t["path"] in failed_paths]

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            for task in retry_tasks:
                f.write(json.dumps(task, ensure_ascii=False) + "\n")

        completed_count = len(calc_success)
        failed_count = len(failed_paths)

        stages = {
            "olp": {
                "input": total_tasks,
                "output": len(olp_success),
                "failed": total_tasks - len(olp_success),
            },
            "infer": {
                "input": len(olp_success),
                "output": len(infer_success),
                "failed": len(olp_success) - len(infer_success),
            },
            "calc": {
                "input": len(infer_success),
                "output": len(calc_success),
                "failed": len(infer_success) - len(calc_success),
            },
        }

        print("\n=== 批量工作流完成情况统计 ===\n")
        for stage_name, stats in stages.items():
            inp = stats["input"]
            out = stats["output"]
            fail = stats["failed"]
            pct = out / inp * 100 if inp > 0 else 0.0

            if fail == 0:
                status = "✓"
            else:
                status = f"- {fail} failed"

            print(
                f"{stage_name.upper():6s}: {inp:4d} → {out:4d} ({pct:5.1f}%) {status}"
            )

        pct_total = completed_count / total_tasks * 100 if total_tasks > 0 else 0.0
        print(f"\n总计: {completed_count}/{total_tasks} 完成 ({pct_total:.1f}%)\n")
        print(f"✓ 已保存 {len(retry_tasks)} 个未完成任务到: {output_file}\n")

        return {
            "total": total_tasks,
            "completed": completed_count,
            "failed": failed_count,
            "stages": stages,
            "output_file": str(output_file),
        }


class BatchWorkflowManager(BatchScheduler):
    """Legacy alias for BatchScheduler."""

    pass
