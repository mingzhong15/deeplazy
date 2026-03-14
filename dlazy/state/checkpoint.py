"""Checkpoint manager for workflow state persistence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dlazy.core.recovery.checksum import compute_checksum, verify_checksum
from dlazy.utils.concurrency import atomic_write_json


class Checkpoint:
    """Checkpoint for a task's output.

    Attributes:
        task_id: ID of the task
        stage: Stage name (olp, infer, calc)
        output_path: Path to output file
        checksum: xxh64 checksum of output
        timestamp: When checkpoint was created
    """

    def __init__(
        self,
        task_id: str,
        stage: str,
        output_path: str,
        checksum: str = "",
        timestamp: Optional[str] = None,
    ):
        """Initialize checkpoint.

        Args:
            task_id: Task identifier
            stage: Stage name
            output_path: Path to output file
            checksum: File checksum
            timestamp: Creation timestamp
        """
        self.task_id = task_id
        self.stage = stage
        self.output_path = output_path
        self.checksum = checksum
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "stage": self.stage,
            "output_path": self.output_path,
            "checksum": self.checksum,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """Create from dictionary."""
        return cls(
            task_id=data["task_id"],
            stage=data["stage"],
            output_path=data["output_path"],
            checksum=data.get("checksum", ""),
            timestamp=data.get("timestamp"),
        )


class CheckpointManager:
    """Manager for task checkpoints.

    Provides checkpoint save, verification, and loading.
    """

    def __init__(
        self,
        checkpoint_dir: Path,
        checkpoint_file: str = "checkpoints.json",
    ):
        """Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory for checkpoint files
            checkpoint_file: Name of checkpoint index file
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_file = self.checkpoint_dir / checkpoint_file
        self._checkpoints: Dict[str, Checkpoint] = {}

        self._load_checkpoints()

    def _load_checkpoints(self) -> None:
        """Load checkpoints from file."""
        if not self.checkpoint_file.exists():
            return

        try:
            with open(self.checkpoint_file, "r") as f:
                data = json.load(f)

            for cp_data in data.get("checkpoints", []):
                cp = Checkpoint.from_dict(cp_data)
                self._checkpoints[cp.task_id] = cp
        except Exception:
            pass

    def _save_checkpoints(self) -> None:
        """Save checkpoints to file."""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "checkpoints": [cp.to_dict() for cp in self._checkpoints.values()],
            "updated_at": datetime.now().isoformat(),
        }

        atomic_write_json(self.checkpoint_file, data)

    def save_checkpoint(
        self,
        task_id: str,
        output_path: str,
        stage: str,
    ) -> Checkpoint:
        """Save a checkpoint for a task.

        Args:
            task_id: Task identifier
            output_path: Path to output file
            stage: Stage name

        Returns:
            Created checkpoint
        """
        output_file = Path(output_path)

        checksum = ""
        if output_file.exists():
            checksum = compute_checksum(output_file)

        checkpoint = Checkpoint(
            task_id=task_id,
            stage=stage,
            output_path=str(output_path),
            checksum=checksum,
        )

        self._checkpoints[task_id] = checkpoint
        self._save_checkpoints()

        return checkpoint

    def verify_checkpoint(self, task_id: str) -> bool:
        """Verify checkpoint for a task.

        Args:
            task_id: Task identifier

        Returns:
            True if checkpoint is valid
        """
        checkpoint = self._checkpoints.get(task_id)
        if checkpoint is None:
            return False

        output_path = Path(checkpoint.output_path)
        if not output_path.exists():
            return False

        if not checkpoint.checksum:
            return True  # No checksum to verify

        return verify_checksum(output_path, checkpoint.checksum)

    def load_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        """Load checkpoint for a task.

        Args:
            task_id: Task identifier

        Returns:
            Checkpoint or None if not found
        """
        return self._checkpoints.get(task_id)

    def delete_checkpoint(self, task_id: str) -> bool:
        """Delete checkpoint for a task.

        Args:
            task_id: Task identifier

        Returns:
            True if checkpoint was deleted
        """
        if task_id in self._checkpoints:
            del self._checkpoints[task_id]
            self._save_checkpoints()
            return True
        return False

    def list_checkpoints(self, stage: Optional[str] = None) -> List[Checkpoint]:
        """List all checkpoints, optionally filtered by stage.

        Args:
            stage: Stage name to filter by

        Returns:
            List of checkpoints
        """
        checkpoints = list(self._checkpoints.values())

        if stage:
            checkpoints = [cp for cp in checkpoints if cp.stage == stage]

        return checkpoints

    def get_verified_outputs(self, stage: str) -> List[str]:
        """Get list of verified output paths for a stage.

        Args:
            stage: Stage name

        Returns:
            List of verified output paths
        """
        outputs = []

        for cp in self.list_checkpoints(stage):
            if self.verify_checkpoint(cp.task_id):
                outputs.append(cp.output_path)

        return outputs

    def get_failed_tasks(self, stage: str) -> List[str]:
        """Get list of task IDs with invalid checkpoints.

        Args:
            stage: Stage name

        Returns:
            List of failed task IDs
        """
        failed = []

        for cp in self.list_checkpoints(stage):
            if not self.verify_checkpoint(cp.task_id):
                failed.append(cp.task_id)

        return failed

    def clear_stage(self, stage: str) -> int:
        """Clear all checkpoints for a stage.

        Args:
            stage: Stage name

        Returns:
            Number of checkpoints cleared
        """
        count = 0
        task_ids = [
            cp.task_id for cp in self._checkpoints.values() if cp.stage == stage
        ]

        for task_id in task_ids:
            del self._checkpoints[task_id]
            count += 1

        if count > 0:
            self._save_checkpoints()

        return count

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._checkpoints

    def __len__(self) -> int:
        return len(self._checkpoints)
