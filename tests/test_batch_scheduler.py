"""Tests for BatchScheduler."""

import json
from pathlib import Path

import pytest

from dlazy.batch_workflow import BatchScheduler
from dlazy.contexts import BatchContext
from dlazy.path_resolver import BatchPathResolver


class TestBatchSchedulerInit:
    """Tests for BatchScheduler initialization."""

    def test_init_creates_state(self, tmp_path):
        """Test that BatchScheduler initializes state."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)

        assert scheduler.state is not None
        assert scheduler.state["current_batch"] == 0
        assert scheduler.state["current_stage"] == "olp"
        assert scheduler.state["completed_batches"] == []

    def test_init_loads_existing_state(self, tmp_path):
        """Test that BatchScheduler loads existing state when resume=True."""
        state_file = tmp_path / "batch_state.json"
        existing_state = {
            "current_batch": 5,
            "current_stage": "infer",
            "completed_batches": [0, 1, 2, 3, 4],
            "olp_completed": False,
            "infer_completed": False,
            "calc_completed": False,
        }
        with open(state_file, "w") as f:
            json.dump(existing_state, f)

        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
            resume=True,
            state_file=state_file,
        )
        scheduler = BatchScheduler(ctx)

        assert scheduler.state["current_batch"] == 5
        assert scheduler.state["current_stage"] == "infer"
        assert len(scheduler.state["completed_batches"]) == 5


class TestBatchSchedulerGetPathResolver:
    """Tests for _get_path_resolver method."""

    def test_get_path_resolver_returns_batch_path_resolver(self, tmp_path):
        """Test that _get_path_resolver returns BatchPathResolver."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)

        resolver = scheduler._get_path_resolver(0)

        assert isinstance(resolver, BatchPathResolver)
        assert resolver.batch_index == 0

    def test_get_path_resolver_correct_batch_index(self, tmp_path):
        """Test that _get_path_resolver returns resolver with correct batch index."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)

        resolver = scheduler._get_path_resolver(42)

        assert resolver.batch_index == 42
        assert "batch.00042" in str(resolver.get_workdir())


class TestBatchSchedulerHasMoreBatches:
    """Tests for _has_more_batches method."""

    def test_has_more_batches_true_when_tasks_remain(self, tmp_path):
        """Test that _has_more_batches returns True when tasks remain."""
        todo_list = tmp_path / "todo_list.json"
        with open(todo_list, "w") as f:
            for i in range(200):
                f.write(f'{{"path": "/path/to/task/{i}"}}\n')

        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)

        assert scheduler._has_more_batches() is True

    def test_has_more_batches_false_when_no_tasks(self, tmp_path):
        """Test that _has_more_batches returns False when no tasks remain."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)

        assert scheduler._has_more_batches() is False

    def test_has_more_batches_false_when_all_processed(self, tmp_path):
        """Test that _has_more_batches returns False when all batches processed."""
        todo_list = tmp_path / "todo_list.json"
        with open(todo_list, "w") as f:
            for i in range(100):
                f.write(f'{{"path": "/path/to/task/{i}"}}\n')

        state_file = tmp_path / "batch_state.json"
        state = {
            "current_batch": 1,
            "current_stage": "olp",
            "completed_batches": [0],
            "olp_completed": False,
            "infer_completed": False,
            "calc_completed": False,
        }
        with open(state_file, "w") as f:
            json.dump(state, f)

        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
            resume=True,
            state_file=state_file,
        )
        scheduler = BatchScheduler(ctx)

        assert scheduler._has_more_batches() is False


class TestBatchSchedulerGetNextStage:
    """Tests for _get_next_stage method."""

    def test_get_next_stage_from_olp(self, tmp_path):
        """Test that _get_next_stage returns 'infer' from 'olp'."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)

        assert scheduler._get_next_stage("olp") == "infer"

    def test_get_next_stage_from_infer(self, tmp_path):
        """Test that _get_next_stage returns 'calc' from 'infer'."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)

        assert scheduler._get_next_stage("infer") == "calc"

    def test_get_next_stage_from_calc(self, tmp_path):
        """Test that _get_next_stage returns 'complete' from 'calc'."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)

        assert scheduler._get_next_stage("calc") == "complete"


class TestBatchSchedulerStatePersistence:
    """Tests for state persistence."""

    def test_save_state_persists_to_file(self, tmp_path):
        """Test that _save_state persists state to file."""
        state_file = tmp_path / "batch_state.json"

        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
            state_file=state_file,
        )
        scheduler = BatchScheduler(ctx)

        scheduler.state["current_batch"] = 10
        scheduler.state["completed_batches"].append(5)
        scheduler._save_state()

        assert state_file.exists()
        with open(state_file, "r") as f:
            loaded = json.load(f)
        assert loaded["current_batch"] == 10
        assert 5 in loaded["completed_batches"]

    def test_state_file_created_on_init(self, tmp_path):
        """Test that state file is created during initialization."""
        state_file = tmp_path / "batch_state.json"

        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
            state_file=state_file,
        )
        BatchScheduler(ctx)

        assert state_file.exists()


class TestBatchSchedulerCheckStageStatus:
    """Tests for _check_stage_status method."""

    def test_check_stage_status_pending_when_no_output(self, tmp_path):
        """Test that _check_stage_status returns 'pending' when no output exists."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)
        resolver = scheduler._get_path_resolver(0)

        status = scheduler._check_stage_status("olp", resolver)

        assert status == "pending"

    def test_check_stage_status_completed_when_folders_exists(self, tmp_path):
        """Test that _check_stage_status returns 'completed' when output exists."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)
        resolver = scheduler._get_path_resolver(0)

        folders_file = resolver.get_olp_folders_file()
        folders_file.parent.mkdir(parents=True, exist_ok=True)
        folders_file.write_text("/path/to/task1\n/path/to/task2\n")

        status = scheduler._check_stage_status("olp", resolver)

        assert status == "completed"

    def test_check_infer_stage_status(self, tmp_path):
        """Test _check_stage_status for infer stage."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)
        resolver = scheduler._get_path_resolver(0)

        hamlog_file = resolver.get_infer_hamlog_file()
        hamlog_file.parent.mkdir(parents=True, exist_ok=True)
        hamlog_file.write_text("task1 scf_path1 geth_path1\n")

        status = scheduler._check_stage_status("infer", resolver)

        assert status == "completed"

    def test_check_calc_stage_status(self, tmp_path):
        """Test _check_stage_status for calc stage."""
        ctx = BatchContext(
            config_path=tmp_path / "config.yaml",
            workflow_root=tmp_path,
            batch_size=100,
        )
        scheduler = BatchScheduler(ctx)
        resolver = scheduler._get_path_resolver(0)

        folders_file = resolver.get_calc_folders_file()
        folders_file.parent.mkdir(parents=True, exist_ok=True)
        folders_file.write_text("task1 scf_path1 geth_path1\n")

        status = scheduler._check_stage_status("calc", resolver)

        assert status == "completed"
