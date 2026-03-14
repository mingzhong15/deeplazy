"""Task state tracking module."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from dlazy.utils.concurrency import atomic_write_json


class TaskState(Enum):
    """State of a task in the workflow."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TEMP_FAIL = "temp_fail"  # Temporary failure, can retry
    PERM_FAIL = "perm_fail"  # Permanent failure, no more retries

    def __str__(self) -> str:
        return self.value

    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (TaskState.SUCCESS, TaskState.PERM_FAIL)

    def can_transition_to(self, new_state: TaskState) -> bool:
        """Check if transition to new state is valid."""
        valid_transitions = {
            TaskState.PENDING: {TaskState.RUNNING, TaskState.FAILED},
            TaskState.RUNNING: {
                TaskState.SUCCESS,
                TaskState.FAILED,
                TaskState.TEMP_FAIL,
            },
            TaskState.FAILED: {TaskState.PENDING},  # Retry
            TaskState.TEMP_FAIL: {TaskState.PENDING},  # Retry
            TaskState.SUCCESS: set(),  # Terminal
            TaskState.PERM_FAIL: set(),  # Terminal
        }
        return new_state in valid_transitions.get(self, set())


@dataclass
class TaskStatus:
    """Status information for a task."""

    task_id: str
    state: TaskState
    stage: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: str = ""
    retry_count: int = 0
    checksum: str = ""
    output_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "stage": self.stage,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "checksum": self.checksum,
            "output_path": self.output_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskStatus:
        """Create from dictionary."""
        return cls(
            task_id=data["task_id"],
            state=TaskState(data["state"]),
            stage=data["stage"],
            start_time=datetime.fromisoformat(data["start_time"])
            if data.get("start_time")
            else None,
            end_time=datetime.fromisoformat(data["end_time"])
            if data.get("end_time")
            else None,
            error_message=data.get("error_message", ""),
            retry_count=data.get("retry_count", 0),
            checksum=data.get("checksum", ""),
            output_path=data.get("output_path", ""),
        )


class TaskStateStore:
    """Store for task states with JSON persistence."""

    def __init__(self, state_file: Optional[Path] = None):
        """Initialize the store.

        Args:
            state_file: Path to state file for persistence
        """
        self._tasks: Dict[str, TaskStatus] = {}
        self._state_file = state_file

        if state_file and state_file.exists():
            self._load_from_file(state_file)

    def add(self, task: TaskStatus) -> None:
        """Add a task to the store."""
        self._tasks[task.task_id] = task

    def get(self, task_id: str) -> Optional[TaskStatus]:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def transition(self, task_id: str, new_state: TaskState) -> None:
        """Transition a task to a new state.

        Args:
            task_id: ID of the task
            new_state: New state to transition to

        Raises:
            KeyError: If task not found
            ValueError: If transition is invalid
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        if not task.state.can_transition_to(new_state):
            raise ValueError(f"Invalid transition from {task.state} to {new_state}")

        task.state = new_state

        if new_state == TaskState.RUNNING:
            task.start_time = datetime.now()
        elif new_state.is_terminal():
            task.end_time = datetime.now()

    def get_by_state(self, state: TaskState) -> List[TaskStatus]:
        """Get all tasks in a specific state."""
        return [t for t in self._tasks.values() if t.state == state]

    def get_by_stage(self, stage: str) -> List[TaskStatus]:
        """Get all tasks in a specific stage."""
        return [t for t in self._tasks.values() if t.stage == stage]

    def get_pending(self) -> List[TaskStatus]:
        """Get all pending tasks."""
        return self.get_by_state(TaskState.PENDING)

    def get_running(self) -> List[TaskStatus]:
        """Get all running tasks."""
        return self.get_by_state(TaskState.RUNNING)

    def get_failed(self) -> List[TaskStatus]:
        """Get all failed tasks (both temp and permanent)."""
        return self.get_by_state(TaskState.FAILED) + self.get_by_state(
            TaskState.TEMP_FAIL
        )

    def get_successful(self) -> List[TaskStatus]:
        """Get all successful tasks."""
        return self.get_by_state(TaskState.SUCCESS)

    def count_by_state(self) -> Dict[TaskState, int]:
        """Count tasks by state."""
        counts = {state: 0 for state in TaskState}
        for task in self._tasks.values():
            counts[task.state] += 1
        return counts

    def save(self, path: Optional[Path] = None) -> None:
        """Save state to file.

        Args:
            path: Path to save to (uses state_file if not provided)
        """
        save_path = path or self._state_file
        if save_path is None:
            return

        data = {
            "tasks": [t.to_dict() for t in self._tasks.values()],
            "saved_at": datetime.now().isoformat(),
        }
        atomic_write_json(data, save_path)

    def _load_from_file(self, path: Path) -> None:
        """Load state from file."""
        import json

        with open(path, "r") as f:
            data = json.load(f)

        for task_data in data.get("tasks", []):
            task = TaskStatus.from_dict(task_data)
            self._tasks[task.task_id] = task

    def __len__(self) -> int:
        return len(self._tasks)

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._tasks
