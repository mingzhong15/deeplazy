"""Integration tests for workflow execution."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dlazy.scheduler.base import JobStatus, SubmitConfig
from dlazy.scheduler.job_manager import JobManager
from dlazy.scheduler.slurm import SlurmScheduler
from dlazy.state.task_state import TaskState, TaskStatus, TaskStateStore
from dlazy.state.checkpoint import CheckpointManager
from dlazy.state.serializer import StateSerializer
from dlazy.execution.base import ExecutorContext, TaskResult, TaskStatus as ExecStatus
from dlazy.execution.olp_executor import OlpExecutor
from dlazy.execution.infer_executor import InferExecutor
from dlazy.execution.calc_executor import CalcExecutor
from dlazy.core.tasks import OlpTask, InferTask, CalcTask
from dlazy.core.recovery.strategies import RecoveryStrategyChain


class MockScheduler:
    """Mock scheduler for integration tests."""

    def __init__(self):
        self._job_counter = 1000
        self._status_map = {}

    def submit(self, script_path, config):
        self._job_counter += 1
        job_id = str(self._job_counter)
        self._status_map[job_id] = JobStatus.PENDING
        return job_id

    def check_status(self, job_id):
        return self._status_map.get(job_id, JobStatus.UNKNOWN)

    def set_status(self, job_id, status):
        self._status_map[job_id] = status

    def cancel(self, job_id):
        if job_id in self._status_map:
            self._status_map[job_id] = JobStatus.CANCELLED
            return True
        return False

    def get_job_info(self, job_id):
        return None

    def wait_for_completion(self, job_id, timeout_seconds=86400, poll_interval=60):
        return self._status_map.get(job_id, JobStatus.UNKNOWN)


class TestJobManagerIntegration:
    """Integration tests for JobManager with TaskStateStore."""

    def test_job_lifecycle_with_state_tracking(self):
        """Test complete job lifecycle updates TaskStateStore."""
        scheduler = MockScheduler()
        state_store = TaskStateStore()
        manager = JobManager(scheduler=scheduler, state_store=state_store)

        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "submit.sh"
            script.write_text("#!/bin/bash\necho test")

            config = SubmitConfig(job_name="test_job")

            job_id = manager.submit_job(script, config, task_id="task_001", stage="olp")

            task = state_store.get("task_001")
            assert task.state == TaskState.RUNNING

            scheduler.set_status(job_id, JobStatus.COMPLETED)
            status = manager.wait_for_completion(job_id, poll_interval=0.01)

            assert status == JobStatus.COMPLETED
            task = state_store.get("task_001")
            assert task.state == TaskState.SUCCESS

    def test_multiple_jobs_tracking(self):
        """Test tracking multiple concurrent jobs."""
        scheduler = MockScheduler()
        state_store = TaskStateStore()
        manager = JobManager(scheduler=scheduler, state_store=state_store)

        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "submit.sh"
            script.write_text("#!/bin/bash\necho test")

            config = SubmitConfig(job_name="test")

            job_ids = []
            for i in range(5):
                job_id = manager.submit_job(
                    script, config, task_id=f"task_{i:03d}", stage="olp"
                )
                job_ids.append(job_id)

            active = manager.get_active_jobs()
            assert len(active) == 5

            for job_id in job_ids[:3]:
                scheduler.set_status(job_id, JobStatus.COMPLETED)
                manager.wait_for_completion(job_id, poll_interval=0.01)

            active = manager.get_active_jobs()
            assert len(active) == 2

            success_count = sum(
                1 for t in state_store._tasks.values() if t.state == TaskState.SUCCESS
            )
            assert success_count == 3


class TestCheckpointIntegration:
    """Integration tests for CheckpointManager with state persistence."""

    def test_checkpoint_save_and_resume(self):
        """Test saving and resuming from checkpoint."""
        with tempfile.TemporaryDirectory() as d:
            checkpoint_dir = Path(d)
            manager = CheckpointManager(checkpoint_dir=checkpoint_dir)

            test_file = checkpoint_dir / "test.h5"
            test_file.write_bytes(b"test data content")

            manager.save_checkpoint("task_001", str(test_file), stage="olp")

            assert manager.verify_checkpoint("task_001")

            outputs = manager.get_verified_outputs("olp")
            assert len(outputs) == 1

    def test_checkpoint_state_serializer_integration(self):
        """Test checkpoint works with state serializer."""
        with tempfile.TemporaryDirectory() as d:
            state_file = Path(d) / "state.json"
            checkpoint_dir = Path(d) / "checkpoints"
            checkpoint_dir.mkdir()

            state_store = TaskStateStore()
            state_store.add(
                TaskStatus(task_id="task_001", state=TaskState.SUCCESS, stage="olp")
            )
            state_store.add(
                TaskStatus(task_id="task_002", state=TaskState.RUNNING, stage="infer")
            )

            serializer = StateSerializer()
            serializer.save_to_file(state_store, state_file)

            loaded_store = serializer.load_from_file(state_file)["store"]

            assert len(loaded_store) == 2
            assert loaded_store.get("task_001").state == TaskState.SUCCESS
            assert loaded_store.get("task_002").state == TaskState.RUNNING


class TestRecoveryIntegration:
    """Integration tests for recovery strategies."""

    def test_recovery_chain_with_transient_error(self):
        """Test recovery chain handles transient errors."""
        chain = RecoveryStrategyChain()

        context = {
            "failure_type": "node_error",
            "retry_count": 0,
        }

        assert chain.should_retry(context)
        assert not chain.should_skip(context)
        assert not chain.should_abort(context)

    def test_recovery_chain_with_permanent_error(self):
        """Test recovery chain handles permanent errors."""
        chain = RecoveryStrategyChain()

        context = {
            "failure_type": "config_error",
            "retry_count": 0,
        }

        assert not chain.should_retry(context)
        assert chain.should_skip(context)
        assert not chain.should_abort(context)

    def test_recovery_exceeds_max_retries(self):
        """Test recovery after exceeding max retries."""
        chain = RecoveryStrategyChain()

        context = {
            "failure_type": "node_error",
            "retry_count": 10,
        }

        assert not chain.should_retry(context)


class TestExecutorIntegration:
    """Integration tests for executor pipeline."""

    def test_executor_context_creation(self):
        """Test executor context works with all components."""
        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(
                config={"test": "value"},
                workdir=Path(d),
                stage="olp",
                task_id="task_001",
                batch_id="batch_001",
            )

            assert ctx.stage == "olp"
            assert ctx.task_id == "task_001"
            assert ctx.batch_id == "batch_001"
            assert ctx.workdir.exists()

    def test_olp_executor_prepare(self):
        """Test OLP executor prepare creates working directory."""
        executor = OlpExecutor(openmx_command="echo test")
        task = OlpTask(path="/tmp/test_poscar")

        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(config={}, workdir=Path(d), stage="olp")
            workdir = executor.prepare(task, ctx)

            assert workdir.exists()
            assert workdir.is_dir()

    def test_infer_executor_prepare(self):
        """Test Infer executor prepare creates working directory."""
        executor = InferExecutor(
            transform_command="echo",
            infer_command="echo",
            transform_reverse_command="echo",
        )
        task = InferTask(path="/tmp/test", scf_path="/tmp/scf")

        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(config={}, workdir=Path(d), stage="infer")
            workdir = executor.prepare(task, ctx)

            assert workdir.exists()

    def test_calc_executor_prepare(self):
        """Test Calc executor prepare creates working directory."""
        executor = CalcExecutor(openmx_command="echo test")
        task = CalcTask(path="/tmp/test", geth_path="/tmp/geth")

        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(config={}, workdir=Path(d), stage="calc")
            workdir = executor.prepare(task, ctx)

            assert workdir.exists()


class TestFullWorkflowSimulation:
    """Simulated full workflow tests."""

    def test_three_stage_workflow_state_transitions(self):
        """Test state transitions through OLP → Infer → Calc."""
        state_store = TaskStateStore()

        state_store.add(
            TaskStatus(task_id="olp_001", state=TaskState.PENDING, stage="olp")
        )
        state_store.transition("olp_001", TaskState.RUNNING)
        state_store.transition("olp_001", TaskState.SUCCESS)

        assert state_store.get("olp_001").state == TaskState.SUCCESS

        state_store.add(
            TaskStatus(task_id="infer_001", state=TaskState.PENDING, stage="infer")
        )
        state_store.transition("infer_001", TaskState.RUNNING)
        state_store.transition("infer_001", TaskState.SUCCESS)

        assert state_store.get("infer_001").state == TaskState.SUCCESS

        state_store.add(
            TaskStatus(task_id="calc_001", state=TaskState.PENDING, stage="calc")
        )
        state_store.transition("calc_001", TaskState.RUNNING)
        state_store.transition("calc_001", TaskState.SUCCESS)

        assert state_store.get("calc_001").state == TaskState.SUCCESS

        counts = state_store.count_by_state()
        assert counts.get(TaskState.SUCCESS) == 3

    def test_workflow_with_failure_and_retry(self):
        """Test workflow handles failure and retry."""
        state_store = TaskStateStore()

        state_store.add(
            TaskStatus(
                task_id="calc_001", state=TaskState.PENDING, stage="calc", retry_count=0
            )
        )
        state_store.transition("calc_001", TaskState.RUNNING)
        state_store.transition("calc_001", TaskState.TEMP_FAIL)

        task = state_store.get("calc_001")
        assert task.state == TaskState.TEMP_FAIL

        task.retry_count = 1
        state_store.transition("calc_001", TaskState.PENDING)
        state_store.transition("calc_001", TaskState.RUNNING)
        state_store.transition("calc_001", TaskState.SUCCESS)

        assert state_store.get("calc_001").state == TaskState.SUCCESS
