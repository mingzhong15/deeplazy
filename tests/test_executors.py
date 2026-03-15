"""Tests for task executors."""

import pytest
import tempfile
from pathlib import Path

from dlazy.execution.base import Executor, ExecutorContext, TaskResult, TaskStatus
from dlazy.execution.olp_executor import OlpExecutor
from dlazy.execution.infer_executor import InferExecutor
from dlazy.execution.calc_executor import CalcExecutor
from dlazy.core.tasks import OlpTask, InferTask, CalcTask


class TestExecutorImports:
    """Test that all executors can be imported."""

    def test_import_base_classes(self):
        from dlazy.execution.base import (
            Executor,
            ExecutorContext,
            TaskResult,
            TaskStatus,
        )

        assert Executor is not None
        assert ExecutorContext is not None
        assert TaskResult is not None
        assert TaskStatus is not None

    def test_import_olp_executor(self):
        from dlazy.execution.olp_executor import OlpExecutor

        assert OlpExecutor is not None
        assert issubclass(OlpExecutor, Executor)

    def test_import_infer_executor(self):
        from dlazy.execution.infer_executor import InferExecutor

        assert InferExecutor is not None
        assert issubclass(InferExecutor, Executor)

    def test_import_calc_executor(self):
        from dlazy.execution.calc_executor import CalcExecutor

        assert CalcExecutor is not None
        assert issubclass(CalcExecutor, Executor)


class TestOlpExecutor:
    """Tests for OlpExecutor."""

    def test_instantiation(self):
        executor = OlpExecutor(openmx_command="echo test")
        assert executor.stage == "olp"
        assert executor.openmx_command == "echo test"

    def test_prepare_creates_workdir(self):
        executor = OlpExecutor(openmx_command="echo test")
        task = OlpTask(path="/tmp/test_poscar")

        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(config={}, workdir=Path(d), stage="olp")
            workdir = executor.prepare(task, ctx)
            assert workdir.exists()
            assert workdir.is_dir()

    def test_cleanup_removes_workdir(self):
        executor = OlpExecutor(openmx_command="echo test")
        task = OlpTask(path="/tmp/test_poscar")

        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(config={}, workdir=Path(d), stage="olp")
            workdir = executor.prepare(task, ctx)
            assert workdir.exists()
            executor.cleanup(task, ctx)


class TestInferExecutor:
    """Tests for InferExecutor."""

    def test_instantiation(self):
        executor = InferExecutor(
            transform_command="transform",
            infer_command="infer",
            transform_reverse_command="transform_reverse",
        )
        assert executor.stage == "infer"

    def test_prepare_creates_workdir(self):
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


class TestCalcExecutor:
    """Tests for CalcExecutor."""

    def test_instantiation(self):
        executor = CalcExecutor(openmx_command="echo test")
        assert executor.stage == "calc"

    def test_prepare_creates_workdir(self):
        executor = CalcExecutor(openmx_command="echo test")
        task = CalcTask(path="/tmp/test", geth_path="/tmp/geth")

        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(config={}, workdir=Path(d), stage="calc")
            workdir = executor.prepare(task, ctx)
            assert workdir.exists()


class TestTaskResult:
    """Tests for TaskResult."""

    def test_success_result(self):
        result = TaskResult(status=TaskStatus.SUCCESS)
        assert result.is_success
        assert not result.is_failed

    def test_failed_result(self):
        result = TaskResult(status=TaskStatus.FAILED)
        assert not result.is_success
        assert result.is_failed

    def test_add_error(self):
        result = TaskResult(status=TaskStatus.FAILED)
        result.add_error("Test error")
        assert len(result.errors) == 1
        assert "Test error" in result.errors

    def test_add_warning(self):
        result = TaskResult(status=TaskStatus.SUCCESS)
        result.add_warning("Test warning")
        assert len(result.warnings) == 1


class TestExecutorContext:
    """Tests for ExecutorContext."""

    def test_context_creation(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(
                config={"test": "value"},
                workdir=Path(d),
                stage="olp",
                task_id="task_001",
            )
            assert ctx.stage == "olp"
            assert ctx.task_id == "task_001"
            assert ctx.workdir.exists()

    def test_context_with_string_workdir(self):
        with tempfile.TemporaryDirectory() as d:
            ctx = ExecutorContext(
                config={},
                workdir=d,
                stage="olp",
            )
            assert isinstance(ctx.workdir, Path)
