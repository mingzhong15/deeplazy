"""State serializer for persistence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from dlazy.state.task_state import TaskState, TaskStatus, TaskStateStore
from dlazy.state.checkpoint import Checkpoint, CheckpointManager
from dlazy.utils.concurrency import atomic_write_json


SERIALIZER_VERSION = "1.0.0"


class StateSerializer:
    """Serializer for workflow state.

    Handles serialization and deserialization of TaskStateStore
    and CheckpointManager.
    """

    def __init__(self, version: str = SERIALIZER_VERSION):
        """Initialize serializer.

        Args:
            version: Serializer version string
        """
        self.version = version

    def serialize(self, store: TaskStateStore) -> Dict[str, Any]:
        """Serialize TaskStateStore to dictionary.

        Args:
            store: TaskStateStore to serialize

        Returns:
            Serializable dictionary
        """
        counts = store.count_by_state()
        return {
            "version": self.version,
            "serialized_at": datetime.now().isoformat(),
            "tasks": [task.to_dict() for task in store._tasks.values()],
            "counts": {str(k): v for k, v in counts.items()},
        }

    def deserialize(self, data: Dict[str, Any]) -> TaskStateStore:
        """Deserialize dictionary to TaskStateStore.

        Args:
            data: Serialized data

        Returns:
            TaskStateStore instance
        """
        store = TaskStateStore()

        for task_data in data.get("tasks", []):
            task = TaskStatus.from_dict(task_data)
            store.add(task)

        return store

    def serialize_checkpoint_manager(
        self, manager: CheckpointManager
    ) -> Dict[str, Any]:
        """Serialize CheckpointManager to dictionary.

        Args:
            manager: CheckpointManager to serialize

        Returns:
            Serializable dictionary
        """
        return {
            "version": self.version,
            "serialized_at": datetime.now().isoformat(),
            "checkpoints": [cp.to_dict() for cp in manager._checkpoints.values()],
        }

    def deserialize_checkpoint_manager(
        self,
        data: Dict[str, Any],
        checkpoint_dir: Path,
    ) -> CheckpointManager:
        """Deserialize dictionary to CheckpointManager.

        Args:
            data: Serialized data
            checkpoint_dir: Directory for checkpoints

        Returns:
            CheckpointManager instance
        """
        manager = CheckpointManager(checkpoint_dir=checkpoint_dir)

        for cp_data in data.get("checkpoints", []):
            cp = Checkpoint.from_dict(cp_data)
            manager._checkpoints[cp.task_id] = cp

        return manager

    def save_to_file(
        self,
        store: TaskStateStore,
        path: Path,
        include_checkpoints: bool = False,
        checkpoint_manager: Optional[CheckpointManager] = None,
    ) -> None:
        """Save state to file atomically.

        Args:
            store: TaskStateStore to save
            path: Output file path
            include_checkpoints: Include checkpoint data
            checkpoint_manager: CheckpointManager to include
        """
        data = {
            "version": self.version,
            "serialized_at": datetime.now().isoformat(),
            "task_store": self.serialize(store),
        }

        if include_checkpoints and checkpoint_manager:
            data["checkpoints"] = self.serialize_checkpoint_manager(checkpoint_manager)

        atomic_write_json(path, data)

    def load_from_file(
        self,
        path: Path,
        checkpoint_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Load state from file.

        Args:
            path: Input file path
            checkpoint_dir: Directory for checkpoints (if loading checkpoints)

        Returns:
            Dict with 'store' (TaskStateStore) and optionally 'checkpoint_manager'
        """
        if not path.exists():
            return {"store": TaskStateStore()}

        with open(path, "r") as f:
            data = json.load(f)

        result = {
            "store": self.deserialize(data.get("task_store", {})),
            "version": data.get("version", "unknown"),
        }

        if "checkpoints" in data and checkpoint_dir:
            result["checkpoint_manager"] = self.deserialize_checkpoint_manager(
                data["checkpoints"],
                checkpoint_dir,
            )

        return result

    def validate_serialized_data(self, data: Dict[str, Any]) -> bool:
        """Validate serialized data structure.

        Args:
            data: Data to validate

        Returns:
            True if valid
        """
        required_keys = ["version", "tasks"]
        task_store = data.get("task_store", {})

        for key in required_keys:
            if key not in task_store:
                return False

        # Validate each task
        for task_data in task_store.get("tasks", []):
            if "task_id" not in task_data:
                return False
            if "state" not in task_data:
                return False

            try:
                TaskState(task_data["state"])
            except ValueError:
                return False

        return True


def serialize_store(store: TaskStateStore) -> Dict[str, Any]:
    """Convenience function to serialize a store.

    Args:
        store: TaskStateStore to serialize

    Returns:
        Serialized dictionary
    """
    return StateSerializer().serialize(store)


def deserialize_store(data: Dict[str, Any]) -> TaskStateStore:
    """Convenience function to deserialize a store.

    Args:
        data: Serialized data

    Returns:
        TaskStateStore instance
    """
    return StateSerializer().deserialize(data)


def save_state(store: TaskStateStore, path: Path) -> None:
    """Convenience function to save state.

    Args:
        store: TaskStateStore to save
        path: Output file path
    """
    StateSerializer().save_to_file(store, path)


def load_state(path: Path) -> TaskStateStore:
    """Convenience function to load state.

    Args:
        path: Input file path

    Returns:
        TaskStateStore instance
    """
    result = StateSerializer().load_from_file(path)
    return result["store"]
