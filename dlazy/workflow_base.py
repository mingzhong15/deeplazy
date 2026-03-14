"""Workflow base class with shared Monitor management logic."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from .constants import DEFAULT_MAX_RETRIES, MONITOR_STATE_FILE
from .core.exceptions import FailureType
from .core.workflow_state import JobMonitor, MonitorConfig, TaskError
from .utils.concurrency import atomic_write_json

if TYPE_CHECKING:
    pass


class WorkflowBase:
    """Base class for workflow managers with Monitor support."""

    def __init__(self):
        self.monitor: Optional[JobMonitor] = None
        self.logger = logging.getLogger(__name__)

    def _init_monitor(
        self,
        max_retries: Optional[Dict[FailureType, int]] = None,
        monitor_state_file: Optional[Path] = None,
    ) -> None:
        """Initialize JobMonitor with config."""
        if max_retries is None:
            max_retries = DEFAULT_MAX_RETRIES

        monitor_config = MonitorConfig(max_retries=max_retries)
        self.monitor = JobMonitor(monitor_config)

        if monitor_state_file and monitor_state_file.exists():
            try:
                with open(monitor_state_file, "r", encoding="utf-8") as f:
                    monitor_state = json.load(f)
                    self.monitor.restore_from_state(monitor_state)
                    self.logger.info(
                        "Restored monitor state from %s", monitor_state_file
                    )
            except Exception as e:
                self.logger.warning("Failed to restore monitor state: %s", e)

    def _save_monitor_state(self, monitor_state_file: Path) -> None:
        """Save monitor state to file."""
        if self.monitor is None:
            return
        try:
            monitor_state = self.monitor.save_state()
            atomic_write_json(monitor_state_file, monitor_state)
        except Exception as e:
            self.logger.error("Failed to save monitor state: %s", e)

    def _check_abort(self) -> bool:
        """Check if workflow should abort."""
        if self.monitor and self.monitor.should_abort():
            self.logger.error(
                "Workflow abort triggered: %s", self.monitor.state.abort_reason
            )
            return True
        return False

    def _report_error(
        self, stage: str, failure_type: FailureType, message: str
    ) -> None:
        """Report task error to monitor."""
        if self.monitor:
            error = TaskError(
                stage=stage,
                failure_type=failure_type,
                message=message,
                timestamp=datetime.now(),
            )
            self.monitor.report_error(error)

    def _get_abort_reason(self) -> Optional[str]:
        """Get abort reason if workflow was aborted."""
        if self.monitor:
            return self.monitor.state.abort_reason
        return None

    def _set_job_id(self, job_id: str) -> None:
        """Set current job ID in monitor."""
        if self.monitor:
            self.monitor.state.job_id = job_id
