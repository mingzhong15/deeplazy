"""Job Manager for SLURM job lifecycle management."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from dlazy.scheduler.base import JobInfo, JobStatus, Scheduler, SubmitConfig

if TYPE_CHECKING:
    from dlazy.state.task_state import TaskStateStore, TaskState


class JobManager:
    """Manager for SLURM job lifecycle.

    Wraps Scheduler with state tracking and provides high-level
    job management operations.
    """

    def __init__(
        self,
        scheduler: Scheduler,
        state_store: Optional["TaskStateStore"] = None,
        poll_interval: int = 60,
    ):
        """Initialize JobManager.

        Args:
            scheduler: Scheduler instance (e.g., SlurmScheduler)
            state_store: Optional TaskStateStore for state tracking
            poll_interval: Default polling interval in seconds
        """
        self.scheduler = scheduler
        self.state_store = state_store
        self.poll_interval = poll_interval

        self._active_jobs: Dict[str, Dict] = {}
        self._job_to_task: Dict[str, str] = {}

    def submit_job(
        self,
        script_path: Path,
        config: SubmitConfig,
        task_id: Optional[str] = None,
        stage: str = "unknown",
    ) -> str:
        """Submit a job and track it.

        Args:
            script_path: Path to job script
            config: Submission configuration
            task_id: Optional task ID for state tracking
            stage: Stage name for state tracking

        Returns:
            Job ID string

        Raises:
            SchedulerError: If submission fails
        """
        job_id = self.scheduler.submit(script_path, config)

        now = datetime.now()
        self._active_jobs[job_id] = {
            "job_id": job_id,
            "job_name": config.job_name,
            "submit_time": now,
            "nodes": config.nodes,
            "ppn": config.ppn,
            "partition": config.partition,
            "time_limit": config.time_limit,
            "task_id": task_id,
            "stage": stage,
        }

        if task_id:
            self._job_to_task[job_id] = task_id

        if task_id:
            self._job_to_task[job_id] = task_id

            if self.state_store is not None:
                from dlazy.state.task_state import TaskState, TaskStatus

                existing = self.state_store.get(task_id)
                if existing:
                    self.state_store.transition(task_id, TaskState.RUNNING)
                else:
                    self.state_store.add(
                        TaskStatus(
                            task_id=task_id,
                            state=TaskState.RUNNING,
                            stage=stage,
                            start_time=now,
                        )
                    )

        return job_id

    def check_status(self, job_id: str) -> JobStatus:
        """Check job status.

        Args:
            job_id: Job ID to check

        Returns:
            JobStatus enum value
        """
        return self.scheduler.check_status(job_id)

    def wait_for_completion(
        self,
        job_id: str,
        timeout_seconds: int = 86400,
        poll_interval: Optional[int] = None,
    ) -> JobStatus:
        """Wait for job to complete.

        Args:
            job_id: Job ID to wait for
            timeout_seconds: Maximum wait time
            poll_interval: Polling interval (uses default if None)

        Returns:
            Final JobStatus
        """
        poll = poll_interval or self.poll_interval
        status = self.scheduler.wait_for_completion(
            job_id, timeout_seconds=timeout_seconds, poll_interval=poll
        )

        self._update_task_state(job_id, status)

        if status.is_terminal():
            self._remove_active_job(job_id)

        return status

    def get_active_jobs(self) -> List[str]:
        """Get list of active job IDs.

        Returns:
            List of job IDs that are PENDING or RUNNING
        """
        active = []
        for job_id in list(self._active_jobs.keys()):
            status = self.scheduler.check_status(job_id)
            if status in (JobStatus.PENDING, JobStatus.RUNNING):
                active.append(job_id)
            else:
                self._remove_active_job(job_id)

        return active

    def get_job_metadata(self, job_id: str) -> Optional[Dict]:
        """Get metadata for a tracked job.

        Args:
            job_id: Job ID

        Returns:
            Metadata dict or None if not tracked
        """
        return self._active_jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """Cancel a job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancellation succeeded
        """
        result = self.scheduler.cancel(job_id)

        if result:
            self._update_task_state(job_id, JobStatus.CANCELLED)
            self._remove_active_job(job_id)

        return result

    def cancel_all(self) -> int:
        """Cancel all active jobs.

        Returns:
            Number of jobs successfully cancelled
        """
        cancelled = 0
        for job_id in self.get_active_jobs():
            if self.cancel(job_id):
                cancelled += 1

        return cancelled

    def get_job_info(self, job_id: str) -> Optional[JobInfo]:
        """Get detailed job information.

        Args:
            job_id: Job ID to query

        Returns:
            JobInfo if found, None otherwise
        """
        return self.scheduler.get_job_info(job_id)

    def get_task_id_for_job(self, job_id: str) -> Optional[str]:
        """Get task ID associated with a job.

        Args:
            job_id: Job ID

        Returns:
            Task ID or None
        """
        return self._job_to_task.get(job_id)

    def _update_task_state(self, job_id: str, status: JobStatus) -> None:
        """Update task state based on job status.

        Args:
            job_id: Job ID
            status: Job status
        """
        if self.state_store is None:
            return

        task_id = self._job_to_task.get(job_id)
        if not task_id:
            return

        from dlazy.state.task_state import TaskState

        state_map = {
            JobStatus.COMPLETED: TaskState.SUCCESS,
            JobStatus.FAILED: TaskState.FAILED,
            JobStatus.CANCELLED: TaskState.FAILED,
            JobStatus.TIMEOUT: TaskState.TEMP_FAIL,
            JobStatus.NODE_FAIL: TaskState.TEMP_FAIL,
        }

        new_state = state_map.get(status)
        if new_state:
            task = self.state_store.get(task_id)
            if task:
                if new_state == TaskState.SUCCESS:
                    task.end_time = datetime.now()
                elif new_state in (TaskState.FAILED, TaskState.TEMP_FAIL):
                    task.end_time = datetime.now()
                    task.error_message = f"Job {job_id} ended with status {status}"

                self.state_store.transition(task_id, new_state)

    def _remove_active_job(self, job_id: str) -> None:
        """Remove job from active tracking.

        Args:
            job_id: Job ID to remove
        """
        self._active_jobs.pop(job_id, None)

    def __len__(self) -> int:
        """Return number of tracked jobs."""
        return len(self._active_jobs)

    def __contains__(self, job_id: str) -> bool:
        """Check if job is being tracked."""
        return job_id in self._active_jobs
