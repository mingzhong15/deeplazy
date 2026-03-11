"""Batch workflow manager for large-scale structure calculations."""

from __future__ import annotations

import json
import multiprocessing
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .commands import CalcCommandExecutor, InferCommandExecutor, OLPCommandExecutor
from .constants import (
    BATCH_STATE_FILE,
    CALC_TASKS_FILE,
    DEFAULT_MAX_RETRIES,
    ERROR_TASKS_FILE,
    INFER_TASKS_FILE,
    MONITOR_STATE_FILE,
    OLP_TASKS_FILE,
)
from .contexts import BatchContext
from .exceptions import AbortException, FailureType
from .monitor import JobMonitor, MonitorConfig, TaskError
from .record_utils import (
    CalcTask,
    ErrorTask,
    InferTask,
    OlpTask,
    append_error_task,
    read_calc_tasks,
    read_infer_tasks,
    read_olp_tasks,
    write_calc_tasks,
    write_infer_tasks,
    write_olp_tasks,
)
from .utils import (
    ensure_directory,
    get_batch_dir,
    get_logger,
    get_task_dir,
    load_global_config_section,
    load_yaml_config,
)


class BatchWorkflowManager:
    """Manages batch iterative computation for large-scale structure calculations."""

    def __init__(self, ctx: BatchContext):
        self.ctx = ctx
        self.logger = get_logger("batch_workflow")
        self.state: Dict[str, Any] = self._load_or_init_state()
        self.monitor: Optional[JobMonitor] = None
        self._init_monitor()

    def _init_monitor(self) -> None:
        """Initialize monitor for error tracking."""
        if self.ctx.monitor is not None:
            self.monitor = self.ctx.monitor
            return

        monitor_config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        self.monitor = JobMonitor(monitor_config)

        monitor_state_file = self.ctx.workflow_root / MONITOR_STATE_FILE
        if monitor_state_file.exists():
            with open(monitor_state_file, "r", encoding="utf-8") as f:
                monitor_state = json.load(f)
                self.monitor.restore_from_state(monitor_state)
                self.logger.info("Restored monitor state from %s", monitor_state_file)

    def _save_monitor_state(self) -> None:
        """Save monitor state to file."""
        if self.monitor is None:
            return
        monitor_state_file = self.ctx.workflow_root / MONITOR_STATE_FILE
        ensure_directory(monitor_state_file.parent)
        with open(monitor_state_file, "w", encoding="utf-8") as f:
            json.dump(self.monitor.save_state(), f, indent=2)

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
            "olp_completed": False,
            "infer_completed": False,
            "calc_completed": False,
        }
        self._save_state(state)
        return state

    def _save_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        """Save current state to file."""
        if state is None:
            state = self.state
        ensure_directory(self.ctx.state_file.parent)
        with open(self.ctx.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _get_tasks_file(self, stage: str, batch_dir: Optional[Path] = None) -> Path:
        """Get tasks file path for a stage."""
        if batch_dir is None:
            batch_dir = get_batch_dir(
                self.ctx.workflow_root, self.state["current_batch"]
            )

        filenames = {
            "olp": OLP_TASKS_FILE,
            "infer": INFER_TASKS_FILE,
            "calc": CALC_TASKS_FILE,
            "error": ERROR_TASKS_FILE,
        }
        return batch_dir / filenames[stage]

    def run(self) -> Dict[str, Any]:
        """Run the complete batch workflow."""
        self.logger.info(
            "Starting batch workflow with batch_size=%d", self.ctx.batch_size
        )

        config = load_yaml_config(self.ctx.config_path)
        olp_config = load_global_config_section(self.ctx.config_path, "0olp")
        infer_config = load_global_config_section(self.ctx.config_path, "1infer")
        calc_config = load_global_config_section(self.ctx.config_path, "2calc")

        try:
            while True:
                batch_index = self.state["current_batch"]
                batch_dir = get_batch_dir(self.ctx.workflow_root, batch_index)
                ensure_directory(batch_dir)

                self.logger.info("Processing batch %d", batch_index)

                if not self.state.get("olp_completed"):
                    self._run_olp_batch(batch_dir, olp_config)
                    self.state["olp_completed"] = True
                    self._save_state()
                    self._save_monitor_state()

                if self.monitor and self.monitor.should_abort():
                    raise AbortException(
                        self.monitor.state.abort_reason or "Max retries exceeded"
                    )

                if not self.state.get("infer_completed"):
                    self._run_infer_batch(
                        batch_dir, infer_config, config.get("software", {})
                    )
                    self.state["infer_completed"] = True
                    self._save_state()
                    self._save_monitor_state()

                if self.monitor and self.monitor.should_abort():
                    raise AbortException(
                        self.monitor.state.abort_reason or "Max retries exceeded"
                    )

                if not self.state.get("calc_completed"):
                    self._run_calc_batch(batch_dir, calc_config)
                    self.state["calc_completed"] = True
                    self._save_state()
                    self._save_monitor_state()

                if self.monitor and self.monitor.should_abort():
                    raise AbortException(
                        self.monitor.state.abort_reason or "Max retries exceeded"
                    )

                self.state["completed_batches"].append(batch_index)
                self.state["current_batch"] = batch_index + 1
                self.state["olp_completed"] = False
                self.state["infer_completed"] = False
                self.state["calc_completed"] = False
                self._save_state()
                self._save_monitor_state()

                olp_tasks_file = self._get_tasks_file("olp", batch_dir)
                if not olp_tasks_file.exists():
                    self.logger.info("No more OLP tasks, workflow complete")
                    break

            self.logger.info("Batch workflow completed")
            return {
                "status": "completed",
                "batches": len(self.state["completed_batches"]),
            }

        except AbortException as e:
            self.logger.error("Batch workflow aborted: %s", e.reason)
            self._save_state()
            self._save_monitor_state()
            return {
                "status": "aborted",
                "reason": e.reason,
                "batches": len(self.state["completed_batches"]),
            }

    def _run_olp_batch(self, batch_dir: Path, config: Dict[str, Any]) -> None:
        """Run OLP stage for current batch."""
        self.logger.info("Running OLP batch in %s", batch_dir)

        olp_tasks_file = self._get_tasks_file("olp", batch_dir)

        if olp_tasks_file.exists():
            tasks = read_olp_tasks(olp_tasks_file)
        else:
            tasks = self._prepare_olp_tasks(batch_dir)
            write_olp_tasks(olp_tasks_file, tasks)

        if not tasks:
            self.logger.info("No OLP tasks to process")
            return

        infer_tasks: List[InferTask] = []
        error_file = self._get_tasks_file("error", batch_dir)

        def process_task(indexed_task):
            idx, task = indexed_task
            try:
                return OLPCommandExecutor.execute_batch(
                    task_index=idx,
                    poscar_path=task.poscar_path,
                    batch_dir=batch_dir,
                    config=config,
                )
            except Exception as e:
                return ErrorTask(
                    poscar_path=task.poscar_path,
                    stage="olp",
                    error=str(e),
                    batch_id=batch_dir.name.split(".")[-1],
                    task_id=f"{idx:06d}",
                )

        with multiprocessing.Pool(processes=1) as pool:
            results = pool.map(process_task, enumerate(tasks))

        for result in results:
            if isinstance(result, InferTask):
                infer_tasks.append(result)
            elif isinstance(result, ErrorTask):
                append_error_task(error_file, result)
                if self.monitor:
                    self.monitor.report_error(
                        TaskError(
                            stage="olp",
                            failure_type=FailureType.CALC_ERROR,
                            message=result.error,
                            timestamp=datetime.now(),
                        )
                    )

        infer_tasks_file = self._get_tasks_file("infer", batch_dir)
        write_infer_tasks(infer_tasks_file, infer_tasks)

        self.logger.info(
            "OLP batch complete: %d success, %d errors",
            len(infer_tasks),
            len(tasks) - len(infer_tasks),
        )

    def _run_infer_batch(
        self, batch_dir: Path, config: Dict[str, Any], software_config: Dict[str, Any]
    ) -> None:
        """Run Infer stage for current batch."""
        self.logger.info("Running Infer batch in %s", batch_dir)

        infer_tasks_file = self._get_tasks_file("infer", batch_dir)
        if not infer_tasks_file.exists():
            self.logger.info("No Infer tasks file, skipping")
            return

        tasks = read_infer_tasks(infer_tasks_file)
        if not tasks:
            self.logger.info("No Infer tasks to process")
            return

        calc_tasks: List[CalcTask] = []
        error_file = self._get_tasks_file("error", batch_dir)

        model_dir = Path(config.get("model_dir", ""))
        dataset_prefix = config.get("dataset_prefix", "dataset")
        parallel = config.get("parallel", 1)

        def process_task(indexed_task):
            idx, task = indexed_task
            try:
                return InferCommandExecutor.execute_batch(
                    task_index=idx,
                    infer_task=task,
                    batch_dir=batch_dir,
                    config=config,
                    model_dir=model_dir,
                    dataset_prefix=dataset_prefix,
                    parallel=parallel,
                )
            except Exception as e:
                return ErrorTask(
                    poscar_path=task.poscar_path,
                    stage="infer",
                    error=str(e),
                    batch_id=batch_dir.name.split(".")[-1],
                    task_id=f"{idx:06d}",
                )

        with multiprocessing.Pool(processes=1) as pool:
            results = pool.map(process_task, enumerate(tasks))

        for result in results:
            if isinstance(result, CalcTask):
                calc_tasks.append(result)
            elif isinstance(result, ErrorTask):
                append_error_task(error_file, result)
                if self.monitor:
                    self.monitor.report_error(
                        TaskError(
                            stage="infer",
                            failure_type=FailureType.CALC_ERROR,
                            message=result.error,
                            timestamp=datetime.now(),
                        )
                    )

        calc_tasks_file = self._get_tasks_file("calc", batch_dir)
        write_calc_tasks(calc_tasks_file, calc_tasks)

        self.logger.info(
            "Infer batch complete: %d success, %d errors",
            len(calc_tasks),
            len(tasks) - len(calc_tasks),
        )

    def _run_calc_batch(self, batch_dir: Path, config: Dict[str, Any]) -> None:
        """Run Calc stage for current batch."""
        self.logger.info("Running Calc batch in %s", batch_dir)

        calc_tasks_file = self._get_tasks_file("calc", batch_dir)
        if not calc_tasks_file.exists():
            self.logger.info("No Calc tasks file, skipping")
            return

        tasks = read_calc_tasks(calc_tasks_file)
        if not tasks:
            self.logger.info("No Calc tasks to process")
            return

        error_file = self._get_tasks_file("error", batch_dir)
        success_count = 0
        error_count = 0

        def process_task(indexed_task):
            idx, task = indexed_task
            return CalcCommandExecutor.execute_batch(
                task_index=idx,
                calc_task=task,
                batch_dir=batch_dir,
                config=config,
            )

        with multiprocessing.Pool(processes=1) as pool:
            results = pool.map(process_task, enumerate(tasks))

        for idx, (status, label) in enumerate(results):
            if status == "success":
                success_count += 1
            else:
                error_count += 1
                error_task = ErrorTask(
                    poscar_path=tasks[idx].poscar_path,
                    stage="calc",
                    error=status,
                    batch_id=batch_dir.name.split(".")[-1],
                    task_id=f"{idx:06d}",
                )
                append_error_task(error_file, error_task)
                if self.monitor:
                    self.monitor.report_error(
                        TaskError(
                            stage="calc",
                            failure_type=FailureType.CALC_ERROR,
                            message=status,
                            timestamp=datetime.now(),
                        )
                    )

        self.logger.info(
            "Calc batch complete: %d success, %d errors", success_count, error_count
        )

    def _prepare_olp_tasks(self, batch_dir: Path) -> List[OlpTask]:
        """Prepare OLP tasks for the batch.

        This method should be overridden or configured to provide POSCAR paths.
        Default implementation reads from a poscar_list.txt file.
        """
        poscar_list_file = self.ctx.workflow_root / "poscar_list.txt"
        if not poscar_list_file.exists():
            self.logger.warning("No poscar_list.txt found, cannot prepare tasks")
            return []

        tasks = []
        with open(poscar_list_file, "r", encoding="utf-8") as f:
            for line in f:
                poscar_path = line.strip()
                if poscar_path and not poscar_path.startswith("#"):
                    tasks.append(OlpTask(poscar_path=poscar_path))

        start_idx = len(self.state["completed_batches"]) * self.ctx.batch_size
        end_idx = start_idx + self.ctx.batch_size
        return tasks[start_idx:end_idx]
