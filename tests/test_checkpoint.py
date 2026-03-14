"""Tests for checkpoint manager."""

import pytest

from dlazy.state.checkpoint import Checkpoint, CheckpointManager


class TestCheckpoint:
    """Tests for Checkpoint."""

    def test_checkpoint_creation(self):
        cp = Checkpoint(
            task_id="task_001",
            stage="olp",
            output_path="/path/to/output.h5",
        )

        assert cp.task_id == "task_001"
        assert cp.stage == "olp"
        assert cp.output_path == "/path/to/output.h5"
        assert cp.checksum == ""
        assert cp.timestamp is not None

    def test_checkpoint_with_checksum(self):
        cp = Checkpoint(
            task_id="task_001",
            stage="calc",
            output_path="/path/to/output.h5",
            checksum="abc123",
        )

        assert cp.checksum == "abc123"

    def test_checkpoint_to_dict(self):
        cp = Checkpoint(
            task_id="task_001",
            stage="olp",
            output_path="/path/to/output.h5",
            checksum="abc123",
        )

        data = cp.to_dict()

        assert data["task_id"] == "task_001"
        assert data["stage"] == "olp"
        assert data["output_path"] == "/path/to/output.h5"
        assert data["checksum"] == "abc123"
        assert "timestamp" in data

    def test_checkpoint_from_dict(self):
        data = {
            "task_id": "task_002",
            "stage": "infer",
            "output_path": "/path/to/infer.h5",
            "checksum": "def456",
            "timestamp": "2024-01-01T00:00:00",
        }

        cp = Checkpoint.from_dict(data)

        assert cp.task_id == "task_002"
        assert cp.stage == "infer"
        assert cp.output_path == "/path/to/infer.h5"
        assert cp.checksum == "def456"


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def test_save_checkpoint(self, tmp_path, sample_hdf5):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        cp = manager.save_checkpoint(
            task_id="task_001",
            output_path=str(sample_hdf5),
            stage="olp",
        )

        assert cp.task_id == "task_001"
        assert cp.checksum != ""
        assert "task_001" in manager

    def test_verify_checkpoint(self, tmp_path, sample_hdf5):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        manager.save_checkpoint(
            task_id="task_001",
            output_path=str(sample_hdf5),
            stage="olp",
        )

        assert manager.verify_checkpoint("task_001")

    def test_verify_checkpoint_missing_file(self, tmp_path):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        manager._checkpoints["task_001"] = Checkpoint(
            task_id="task_001",
            stage="olp",
            output_path="/nonexistent/path.h5",
            checksum="abc123",
        )

        assert not manager.verify_checkpoint("task_001")

    def test_load_checkpoint(self, tmp_path, sample_hdf5):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        manager.save_checkpoint(
            task_id="task_001",
            output_path=str(sample_hdf5),
            stage="olp",
        )

        cp = manager.load_checkpoint("task_001")
        assert cp is not None
        assert cp.task_id == "task_001"

    def test_load_checkpoint_not_found(self, tmp_path):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        cp = manager.load_checkpoint("nonexistent")
        assert cp is None

    def test_delete_checkpoint(self, tmp_path, sample_hdf5):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        manager.save_checkpoint(
            task_id="task_001",
            output_path=str(sample_hdf5),
            stage="olp",
        )

        assert manager.delete_checkpoint("task_001")
        assert "task_001" not in manager

    def test_list_checkpoints(self, tmp_path, sample_hdf5):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        manager.save_checkpoint("task_001", str(sample_hdf5), "olp")
        manager.save_checkpoint("task_002", str(sample_hdf5), "infer")
        manager.save_checkpoint("task_003", str(sample_hdf5), "olp")

        all_cps = manager.list_checkpoints()
        assert len(all_cps) == 3

        olp_cps = manager.list_checkpoints(stage="olp")
        assert len(olp_cps) == 2

    def test_get_verified_outputs(self, tmp_path, sample_hdf5):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        manager.save_checkpoint("task_001", str(sample_hdf5), "olp")
        manager.save_checkpoint("task_002", str(sample_hdf5), "olp")

        outputs = manager.get_verified_outputs("olp")
        assert len(outputs) == 2

    def test_get_failed_tasks(self, tmp_path):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        manager._checkpoints["task_001"] = Checkpoint(
            task_id="task_001",
            stage="olp",
            output_path="/nonexistent.h5",
            checksum="abc123",
        )
        manager._save_checkpoints()

        failed = manager.get_failed_tasks("olp")
        assert "task_001" in failed

    def test_clear_stage(self, tmp_path, sample_hdf5):
        manager = CheckpointManager(checkpoint_dir=tmp_path)

        manager.save_checkpoint("task_001", str(sample_hdf5), "olp")
        manager.save_checkpoint("task_002", str(sample_hdf5), "infer")

        count = manager.clear_stage("olp")
        assert count == 1
        assert len(manager.list_checkpoints()) == 1

    def test_persistence(self, tmp_path, sample_hdf5):
        manager1 = CheckpointManager(checkpoint_dir=tmp_path)
        manager1.save_checkpoint("task_001", str(sample_hdf5), "olp")

        manager2 = CheckpointManager(checkpoint_dir=tmp_path)
        assert "task_001" in manager2
