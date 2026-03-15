"""Tests for Job Manager."""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from dlazy.scheduler.base import JobStatus, SubmitConfig
from dlazy.scheduler.job_manager import JobManager
from dlazy.scheduler.slurm import SlurmScheduler
from dlazy.state.task_state import TaskState, TaskStatus, TaskStateStore


class MockScheduler:
    """Mock scheduler for testing."""

    def __init__(self):
        self.submitted_jobs = {}
        self._job_counter = 1000
        self._status_map = {}

    def submit(self, script_path: Path, config: SubmitConfig) -> str:
        self._job_counter += 1
        job_id = str(self._job_counter)
        self.submitted_jobs[job_id] = {
            "script": str(script_path),
            "config": config,
        }
        self._status_map[job_id] = JobStatus.PENDING
        return job_id

    def check_status(self, job_id: str) -> JobStatus:
        return self._status_map.get(job_id, JobStatus.UNKNOWN)

    def set_status(self, job_id: str, status: JobStatus):
        self._status_map[job_id] = status

    def cancel(self, job_id: str) -> bool:
        if job_id in self._status_map:
            self._status_map[job_id] = JobStatus.CANCELLED
            return True
        return False

    def get_job_info(self, job_id: str) -> None:
        return None

    def wait_for_completion(
        self, job_id: str, timeout_seconds: int = 86400, poll_interval: int = 60
    ) -> JobStatus:
        return self._status_map.get(job_id, JobStatus.UNKNOWN)


class TestJobManager:
    """Tests for JobManager."""

    def test_submit_job(self, tmp_path):
        mock_scheduler = MockScheduler()
        manager = JobManager(scheduler=mock_scheduler)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config)

        assert job_id == "1001"
        assert job_id in manager
        assert len(manager) == 1

    def test_submit_job_with_task_id(self, tmp_path):
        mock_scheduler = MockScheduler()
        state_store = TaskStateStore()
        manager = JobManager(scheduler=mock_scheduler, state_store=state_store)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config, task_id="task_001", stage="olp")

        assert job_id == "1001"
        assert manager.get_task_id_for_job(job_id) == "task_001"

        task = state_store.get("task_001")
        assert task is not None
        assert task.state == TaskState.RUNNING
        assert task.stage == "olp"

    def test_check_status(self, tmp_path):
        mock_scheduler = MockScheduler()
        manager = JobManager(scheduler=mock_scheduler)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config)

        assert manager.check_status(job_id) == JobStatus.PENDING

        mock_scheduler.set_status(job_id, JobStatus.RUNNING)
        assert manager.check_status(job_id) == JobStatus.RUNNING

    def test_wait_for_completion_success(self, tmp_path):
        mock_scheduler = MockScheduler()
        manager = JobManager(scheduler=mock_scheduler)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config)

        mock_scheduler.set_status(job_id, JobStatus.COMPLETED)
        status = manager.wait_for_completion(job_id, poll_interval=0.01)

        assert status == JobStatus.COMPLETED
        assert job_id not in manager

    def test_wait_for_completion_updates_task_state(self, tmp_path):
        mock_scheduler = MockScheduler()
        state_store = TaskStateStore()
        manager = JobManager(scheduler=mock_scheduler, state_store=state_store)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config, task_id="task_001", stage="olp")

        mock_scheduler.set_status(job_id, JobStatus.COMPLETED)
        manager.wait_for_completion(job_id, poll_interval=0.01)

        task = state_store.get("task_001")
        assert task.state == TaskState.SUCCESS
        assert task.end_time is not None

    def test_get_active_jobs(self, tmp_path):
        mock_scheduler = MockScheduler()
        manager = JobManager(scheduler=mock_scheduler)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id1 = manager.submit_job(script, config)
        job_id2 = manager.submit_job(script, config)

        mock_scheduler.set_status(job_id1, JobStatus.RUNNING)
        mock_scheduler.set_status(job_id2, JobStatus.PENDING)

        active = manager.get_active_jobs()
        assert len(active) == 2
        assert job_id1 in active
        assert job_id2 in active

    def test_get_active_jobs_excludes_completed(self, tmp_path):
        mock_scheduler = MockScheduler()
        manager = JobManager(scheduler=mock_scheduler)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id1 = manager.submit_job(script, config)
        job_id2 = manager.submit_job(script, config)

        mock_scheduler.set_status(job_id1, JobStatus.COMPLETED)

        active = manager.get_active_jobs()
        assert len(active) == 1
        assert job_id1 not in active

    def test_cancel(self, tmp_path):
        mock_scheduler = MockScheduler()
        manager = JobManager(scheduler=mock_scheduler)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config)

        result = manager.cancel(job_id)
        assert result is True
        assert manager.check_status(job_id) == JobStatus.CANCELLED
        assert job_id not in manager

    def test_cancel_all(self, tmp_path):
        mock_scheduler = MockScheduler()
        manager = JobManager(scheduler=mock_scheduler)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        for _ in range(3):
            manager.submit_job(script, config)

        cancelled = manager.cancel_all()
        assert cancelled == 3
        assert len(manager.get_active_jobs()) == 0

    def test_get_job_metadata(self, tmp_path):
        mock_scheduler = MockScheduler()
        manager = JobManager(scheduler=mock_scheduler)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job", nodes=2, ppn=48)
        job_id = manager.submit_job(script, config)

        metadata = manager.get_job_metadata(job_id)
        assert metadata is not None
        assert metadata["job_name"] == "test_job"
        assert metadata["nodes"] == 2
        assert metadata["ppn"] == 48

    def test_job_failure_updates_task_state(self, tmp_path):
        mock_scheduler = MockScheduler()
        state_store = TaskStateStore()
        manager = JobManager(scheduler=mock_scheduler, state_store=state_store)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config, task_id="task_001", stage="calc")

        mock_scheduler.set_status(job_id, JobStatus.FAILED)
        manager.wait_for_completion(job_id, poll_interval=0.01)

        task = state_store.get("task_001")
        assert task.state == TaskState.FAILED
        assert "FAILED" in task.error_message

    def test_node_fail_sets_temp_fail(self, tmp_path):
        mock_scheduler = MockScheduler()
        state_store = TaskStateStore()
        manager = JobManager(scheduler=mock_scheduler, state_store=state_store)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config, task_id="task_001", stage="olp")

        mock_scheduler.set_status(job_id, JobStatus.NODE_FAIL)
        manager.wait_for_completion(job_id, poll_interval=0.01)

        task = state_store.get("task_001")
        assert task.state == TaskState.TEMP_FAIL

    def test_timeout_sets_temp_fail(self, tmp_path):
        mock_scheduler = MockScheduler()
        state_store = TaskStateStore()
        manager = JobManager(scheduler=mock_scheduler, state_store=state_store)

        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        config = SubmitConfig(job_name="test_job")
        job_id = manager.submit_job(script, config, task_id="task_001", stage="olp")

        mock_scheduler.set_status(job_id, JobStatus.TIMEOUT)
        manager.wait_for_completion(job_id, poll_interval=0.01)

        task = state_store.get("task_001")
        assert task.state == TaskState.TEMP_FAIL
