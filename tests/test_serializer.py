"""Tests for state serializer."""

import pytest

from dlazy.state.task_state import TaskState, TaskStatus, TaskStateStore
from dlazy.state.checkpoint import Checkpoint
from dlazy.state.serializer import (
    StateSerializer,
    deserialize_store,
    load_state,
    save_state,
    serialize_store,
)


class TestStateSerializer:
    """Tests for StateSerializer."""

    def test_serialize_store(self):
        store = TaskStateStore()
        store.add(TaskStatus(task_id="task_001", state=TaskState.SUCCESS, stage="olp"))
        store.add(TaskStatus(task_id="task_002", state=TaskState.FAILED, stage="olp"))

        serializer = StateSerializer()
        data = serializer.serialize(store)

        assert "tasks" in data
        assert len(data["tasks"]) == 2
        assert "counts" in data

    def test_deserialize_store(self):
        data = {
            "tasks": [
                {"task_id": "task_001", "state": "success", "stage": "olp"},
                {"task_id": "task_002", "state": "failed", "stage": "olp"},
            ],
            "counts": {"success": 1, "failed": 1},
        }

        serializer = StateSerializer()
        store = serializer.deserialize(data)

        assert len(store) == 2
        assert store.get("task_001").state == TaskState.SUCCESS
        assert store.get("task_002").state == TaskState.FAILED

    def test_serialize_deserialize_roundtrip(self):
        store = TaskStateStore()
        store.add(TaskStatus(task_id="task_001", state=TaskState.SUCCESS, stage="olp"))
        store.add(
            TaskStatus(task_id="task_002", state=TaskState.RUNNING, stage="infer")
        )
        store.add(TaskStatus(task_id="task_003", state=TaskState.FAILED, stage="calc"))

        serializer = StateSerializer()
        data = serializer.serialize(store)
        restored = serializer.deserialize(data)

        assert len(restored) == len(store)
        for task_id in ["task_001", "task_002", "task_003"]:
            assert restored.get(task_id).state == store.get(task_id).state

    def test_save_to_file(self, tmp_path):
        store = TaskStateStore()
        store.add(TaskStatus(task_id="task_001", state=TaskState.SUCCESS, stage="olp"))

        serializer = StateSerializer()
        path = tmp_path / "state.json"
        serializer.save_to_file(store, path)

        assert path.exists()

    def test_load_from_file(self, tmp_path):
        store = TaskStateStore()
        store.add(TaskStatus(task_id="task_001", state=TaskState.SUCCESS, stage="olp"))
        store.add(TaskStatus(task_id="task_002", state=TaskState.FAILED, stage="olp"))

        serializer = StateSerializer()
        path = tmp_path / "state.json"
        serializer.save_to_file(store, path)

        result = serializer.load_from_file(path)
        restored = result["store"]

        assert len(restored) == 2

    def test_load_from_nonexistent_file(self, tmp_path):
        serializer = StateSerializer()
        result = serializer.load_from_file(tmp_path / "nonexistent.json")

        assert isinstance(result["store"], TaskStateStore)
        assert len(result["store"]) == 0

    def test_validate_serialized_data(self):
        data = {
            "task_store": {
                "version": "1.0.0",
                "tasks": [
                    {"task_id": "task_001", "state": "success", "stage": "olp"},
                ],
            }
        }

        serializer = StateSerializer()
        assert serializer.validate_serialized_data(data)

    def test_validate_serialized_data_invalid_state(self):
        data = {
            "task_store": {
                "version": "1.0.0",
                "tasks": [
                    {"task_id": "task_001", "state": "invalid_state", "stage": "olp"},
                ],
            }
        }

        serializer = StateSerializer()
        assert not serializer.validate_serialized_data(data)

    def test_validate_serialized_data_missing_task_id(self):
        data = {
            "task_store": {
                "version": "1.0.0",
                "tasks": [
                    {"state": "success", "stage": "olp"},
                ],
            }
        }

        serializer = StateSerializer()
        assert not serializer.validate_serialized_data(data)


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_serialize_store(self):
        store = TaskStateStore()
        store.add(TaskStatus(task_id="task_001", state=TaskState.SUCCESS, stage="olp"))

        data = serialize_store(store)
        assert len(data["tasks"]) == 1

    def test_deserialize_store(self):
        data = {
            "tasks": [
                {"task_id": "task_001", "state": "success", "stage": "olp"},
            ],
            "counts": {"success": 1},
        }

        store = deserialize_store(data)
        assert len(store) == 1

    def test_save_and_load_state(self, tmp_path):
        store = TaskStateStore()
        store.add(TaskStatus(task_id="task_001", state=TaskState.SUCCESS, stage="olp"))
        store.add(
            TaskStatus(task_id="task_002", state=TaskState.RUNNING, stage="infer")
        )

        path = tmp_path / "state.json"
        save_state(store, path)

        restored = load_state(path)
        assert len(restored) == 2
