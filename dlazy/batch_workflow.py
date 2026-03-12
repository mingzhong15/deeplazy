"""Batch workflow scheduler for large-scale structure calculations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .constants import (
    BATCH_STATE_FILE,
    BATCH_STAGES,
    MONITOR_STATE_FILE,
)
from .contexts import BatchContext
from .exceptions import AbortException
from .path_resolver import BatchPathResolver
from .record_utils import OlpTask, _read_jsonl
from .utils import ensure_directory, get_logger, load_yaml_config
from .workflow_base import WorkflowBase

if TYPE_CHECKING:
    pass


class BatchScheduler(WorkflowBase):
    """Manages batch iterative computation with SLURM job submission."""

    def __init__(self, ctx: BatchContext):
        super().__init__()
        self.ctx = ctx
        self.logger = get_logger("batch_scheduler")
        self.state: Dict[str, Any] = self._load_or_init_state()

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
        if self.ctx.state_file is None:
            return
        ensure_directory(self.ctx.state_file.parent)
        with open(self.ctx.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def _get_path_resolver(self, batch_index: int) -> BatchPathResolver:
        """Get PathResolver for a specific batch."""
        return BatchPathResolver(self.ctx.workflow_root, batch_index)

    def _has_more_batches(self) -> bool:
        """Check if there are more batches to process."""
        path_resolver = self._get_path_resolver(self.state["current_batch"])
        todo_list_file = path_resolver.get_todo_list_file()

        if not todo_list_file.exists():
            return False

        with open(todo_list_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_tasks = len(lines)
        start_idx = self.state["current_batch"] * self.ctx.batch_size

        return start_idx < total_tasks

    def _get_next_stage(self, current_stage: str) -> str:
        """Get the next stage in the workflow."""
        stage_order = ["olp", "infer", "calc", "complete"]
        try:
            idx = stage_order.index(current_stage)
            return stage_order[idx + 1]
        except (ValueError, IndexError):
            return "complete"

    def _check_stage_status(self, stage: str, path_resolver: BatchPathResolver) -> str:
        """Check if a stage is pending/running/completed."""
        if stage == "olp":
            folders_file = path_resolver.get_olp_folders_file()
            if folders_file.exists() and folders_file.stat().st_size > 0:
                return "completed"
        elif stage == "infer":
            hamlog_file = path_resolver.get_infer_hamlog_file()
            if hamlog_file.exists() and hamlog_file.stat().st_size > 0:
                return "completed"
        elif stage == "calc":
            folders_file = path_resolver.get_calc_folders_file()
            if folders_file.exists() and folders_file.stat().st_size > 0:
                return "completed"

        return "pending"

    def _prepare_olp_tasks(self, path_resolver: BatchPathResolver) -> List[OlpTask]:
        """Prepare OLP tasks from todo_list.json."""
        todo_list_file = path_resolver.get_todo_list_file()

        if not todo_list_file.exists():
            self.logger.warning("No input file found: %s", todo_list_file)
            return []

        tasks = []
        for d in _read_jsonl(todo_list_file):
            path = d.get("path", "")
            if path:
                tasks.append(OlpTask(path=path))

        start_idx = self.state["current_batch"] * self.ctx.batch_size
        end_idx = start_idx + self.ctx.batch_size
        return tasks[start_idx:end_idx]

    def run(self) -> Dict[str, Any]:
        """Run the batch workflow loop."""
        self.logger.info(
            "Starting batch workflow with batch_size=%d", self.ctx.batch_size
        )

        try:
            while self._has_more_batches():
                batch_index = self.state["current_batch"]
                path_resolver = self._get_path_resolver(batch_index)

                ensure_directory(path_resolver.get_workdir())

                self.logger.info("Processing batch %d", batch_index)

                if not self.state.get("olp_completed"):
                    self._run_olp_stage(path_resolver)
                    self.state["olp_completed"] = True
                    self._save_state()
                    self._save_monitor_state(
                        self.ctx.workflow_root / MONITOR_STATE_FILE
                    )

                if self._check_abort():
                    raise AbortException(
                        self._get_abort_reason() or "Max retries exceeded"
                    )

                if not self.state.get("infer_completed"):
                    self._run_infer_stage(path_resolver)
                    self.state["infer_completed"] = True
                    self._save_state()
                    self._save_monitor_state(
                        self.ctx.workflow_root / MONITOR_STATE_FILE
                    )

                if self._check_abort():
                    raise AbortException(
                        self._get_abort_reason() or "Max retries exceeded"
                    )

                if not self.state.get("calc_completed"):
                    self._run_calc_stage(path_resolver)
                    self.state["calc_completed"] = True
                    self._save_state()
                    self._save_monitor_state(
                        self.ctx.workflow_root / MONITOR_STATE_FILE
                    )

                if self._check_abort():
                    raise AbortException(
                        self._get_abort_reason() or "Max retries exceeded"
                    )

                self.state["completed_batches"].append(batch_index)
                self.state["current_batch"] = batch_index + 1
                self.state["olp_completed"] = False
                self.state["infer_completed"] = False
                self.state["calc_completed"] = False
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

    def _run_olp_stage(self, path_resolver: BatchPathResolver) -> None:
        """Run OLP stage for current batch."""
        self.logger.info("Running OLP stage in %s", path_resolver.get_workdir())

        from .executor import WorkflowExecutor

        config = load_yaml_config(self.ctx.config_path)
        olp_config = config.get("0olp", {})

        start_idx = self.state["current_batch"] * self.ctx.batch_size
        end_idx = start_idx + self.ctx.batch_size

        WorkflowExecutor.run_olp_stage(
            global_config=str(self.ctx.config_path),
            start=start_idx,
            end=end_idx,
            path_resolver=path_resolver,
            monitor=self.monitor,
        )

    def _run_infer_stage(self, path_resolver: BatchPathResolver) -> None:
        """Run Infer stage for current batch."""
        self.logger.info("Running Infer stage in %s", path_resolver.get_workdir())

        from .executor import WorkflowExecutor

        WorkflowExecutor.run_infer_stage(
            global_config=str(self.ctx.config_path),
            group_index=1,
            path_resolver=path_resolver,
        )

    def _run_calc_stage(self, path_resolver: BatchPathResolver) -> None:
        """Run Calc stage for current batch."""
        self.logger.info("Running Calc stage in %s", path_resolver.get_workdir())

        from .executor import WorkflowExecutor

        start_idx = self.state["current_batch"] * self.ctx.batch_size
        end_idx = start_idx + self.ctx.batch_size

        WorkflowExecutor.run_calc_stage(
            global_config=str(self.ctx.config_path),
            start=start_idx,
            end=end_idx,
            path_resolver=path_resolver,
            monitor=self.monitor,
        )


class BatchWorkflowManager(BatchScheduler):
    """Legacy alias for BatchScheduler."""

    pass
