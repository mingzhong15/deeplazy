"""Tests for base classes."""

import pytest
from pathlib import Path
from datetime import datetime

from dlazy.core.validator.base import Validator, ValidationResult
from dlazy.core.recovery.base import RecoveryAction, RecoveryStrategy, RecoveryContext
from dlazy.scheduler.base import (
    JobStatus,
    JobInfo,
    SubmitConfig,
    Scheduler,
    SchedulerError,
)
from dlazy.execution.base import TaskStatus, TaskResult, ExecutorContext, Executor


# ============================================================================
# Validator Tests
# ============================================================================


def test_validation_result_initialization():
    """Test ValidationResult initialization."""
    result = ValidationResult(is_valid=True)
    assert result.is_valid is True
    assert result.errors == []
    assert result.warnings == []
    assert result.details == {}


def test_validation_result_with_data():
    """Test ValidationResult with data."""
    result = ValidationResult(
        is_valid=False,
        errors=["error1", "error2"],
        warnings=["warning1"],
        details={"key": "value"},
    )
    assert result.is_valid is False
    assert len(result.errors) == 2
    assert len(result.warnings) == 1
    assert result.details["key"] == "value"


def test_validation_result_bool():
    """Test ValidationResult boolean conversion."""
    valid = ValidationResult(is_valid=True)
    invalid = ValidationResult(is_valid=False)

    assert bool(valid) is True
    assert bool(invalid) is False


def test_validation_result_merge():
    """Test ValidationResult merge."""
    r1 = ValidationResult(is_valid=True, errors=["e1"], warnings=["w1"])
    r2 = ValidationResult(is_valid=False, errors=["e2"], warnings=["w2"])

    merged = r1.merge(r2)
    assert merged.is_valid is False
    assert "e1" in merged.errors
    assert "e2" in merged.errors


def test_validator_abstract():
    """Test that Validator is abstract and cannot be instantiated."""
    with pytest.raises(TypeError):
        Validator()


def test_validator_subclass():
    """Test Validator subclass implementation."""

    class TestValidator(Validator):
        validator_type = "test"

        def validate(self, path: Path) -> ValidationResult:
            return ValidationResult(is_valid=True, details={"path": str(path)})

    validator = TestValidator()
    result = validator.validate(Path("/tmp/test"))

    assert result.is_valid is True
    assert validator.validator_type == "test"


# ============================================================================
# Recovery Tests
# ============================================================================


def test_recovery_action_enum():
    """Test RecoveryAction enum values."""
    assert RecoveryAction.RETRY.value == "retry"
    assert RecoveryAction.SKIP.value == "skip"
    assert RecoveryAction.ABORT.value == "abort"


def test_recovery_action_str():
    """Test RecoveryAction string conversion."""
    assert str(RecoveryAction.RETRY) == "retry"
    assert str(RecoveryAction.SKIP) == "skip"


def test_recovery_context_builder():
    """Test RecoveryContext builder."""
    context = (
        RecoveryContext()
        .with_failure_type("node_error")
        .with_retry_count(2)
        .with_error_message("Test error")
        .with_task_id("task-001")
        .with_stage("olp")
        .build()
    )

    assert context["failure_type"] == "node_error"
    assert context["retry_count"] == 2
    assert context["error_message"] == "Test error"
    assert context["task_id"] == "task-001"
    assert context["stage"] == "olp"


def test_recovery_strategy_abstract():
    """Test that RecoveryStrategy is abstract."""
    with pytest.raises(TypeError):
        RecoveryStrategy()


# ============================================================================
# Scheduler Tests
# ============================================================================


def test_job_status_enum():
    """Test JobStatus enum values."""
    assert JobStatus.PENDING.value == "PENDING"
    assert JobStatus.RUNNING.value == "RUNNING"
    assert JobStatus.COMPLETED.value == "COMPLETED"
    assert JobStatus.FAILED.value == "FAILED"


def test_job_status_is_terminal():
    """Test JobStatus is_terminal method."""
    assert JobStatus.COMPLETED.is_terminal() is True
    assert JobStatus.FAILED.is_terminal() is True
    assert JobStatus.PENDING.is_terminal() is False
    assert JobStatus.RUNNING.is_terminal() is False


def test_job_status_is_success():
    """Test JobStatus is_success method."""
    assert JobStatus.COMPLETED.is_success() is True
    assert JobStatus.FAILED.is_success() is False


def test_job_info_dataclass():
    """Test JobInfo dataclass."""
    job = JobInfo(
        job_id="12345",
        status=JobStatus.RUNNING,
        submit_time=datetime.now(),
        job_name="test_job",
        nodes=2,
        ppn=24,
    )

    assert job.job_id == "12345"
    assert job.status == JobStatus.RUNNING
    assert job.nodes == 2
    assert job.ppn == 24


def test_submit_config_to_sbatch_args():
    """Test SubmitConfig to_sbatch_args method."""
    config = SubmitConfig(
        job_name="test", nodes=1, ppn=24, time_limit="1:00:00", partition="normal"
    )

    args = config.to_sbatch_args()

    assert "--job-name=test" in args
    assert "--nodes=1" in args
    assert "--ntasks-per-node=24" in args
    assert "--time=1:00:00" in args


def test_scheduler_error():
    """Test SchedulerError exception."""
    error = SchedulerError("Submission failed", job_id="12345")

    assert str(error) == "Submission failed"
    assert error.job_id == "12345"


def test_scheduler_abstract():
    """Test that Scheduler is abstract."""
    with pytest.raises(TypeError):
        Scheduler()


# ============================================================================
# Executor Tests
# ============================================================================


def test_task_status_enum():
    """Test TaskStatus enum values."""
    assert TaskStatus.SUCCESS.value == "success"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.SKIPPED.value == "skipped"


def test_task_result_dataclass():
    """Test TaskResult dataclass."""
    result = TaskResult(
        status=TaskStatus.SUCCESS, output_path=Path("/tmp/output"), errors=["error1"]
    )

    assert result.status == TaskStatus.SUCCESS
    assert result.is_success is True
    assert result.is_failed is False


def test_task_result_add_error():
    """Test TaskResult add_error method."""
    result = TaskResult(status=TaskStatus.SUCCESS)
    result.add_error("New error")

    assert "New error" in result.errors


def test_task_result_add_warning():
    """Test TaskResult add_warning method."""
    result = TaskResult(status=TaskStatus.SUCCESS)
    result.add_warning("New warning")

    assert "New warning" in result.warnings


def test_executor_context():
    """Test ExecutorContext dataclass."""
    ctx = ExecutorContext(
        config={"key": "value"},
        workdir=Path("/tmp/work"),
        stage="olp",
        task_id="task-001",
    )

    assert ctx.config["key"] == "value"
    assert ctx.stage == "olp"
    assert ctx.task_id == "task-001"


def test_executor_context_str_workdir():
    """Test ExecutorContext with string workdir."""
    ctx = ExecutorContext(config={}, workdir="/tmp/work", stage="olp")

    assert isinstance(ctx.workdir, Path)


def test_executor_abstract():
    """Test that Executor is abstract."""
    with pytest.raises(TypeError):
        Executor()
