"""Executor base classes and interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskStatus(Enum):
    """Status of a task execution."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    RUNNING = "running"
    PENDING = "pending"

    def __str__(self) -> str:
        return self.value


@dataclass
class TaskResult:
    """Result of a task execution."""

    status: TaskStatus
    output_path: Optional[Path] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validation_results: List[Any] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """Check if task succeeded."""
        return self.status == TaskStatus.SUCCESS

    @property
    def is_failed(self) -> bool:
        """Check if task failed."""
        return self.status == TaskStatus.FAILED

    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)


@dataclass
class ExecutorContext:
    """Context for task execution."""

    config: Dict[str, Any]
    workdir: Path
    stage: str
    monitor: Optional[Any] = None
    logger: Optional[Any] = None
    task_id: str = ""
    batch_id: str = ""

    def __post_init__(self):
        """Ensure workdir is a Path."""
        if isinstance(self.workdir, str):
            self.workdir = Path(self.workdir)


class Executor(ABC):
    """Abstract base class for task executors.

    Executors handle the actual execution of tasks in the workflow.
    """

    stage: str = "base"

    @abstractmethod
    def prepare(self, task: Any, ctx: ExecutorContext) -> Path:
        """Prepare working directory for task execution.

        Args:
            task: Task to prepare for
            ctx: Execution context

        Returns:
            Path to prepared working directory
        """
        pass

    @abstractmethod
    def execute(self, task: Any, ctx: ExecutorContext) -> TaskResult:
        """Execute the task.

        Args:
            task: Task to execute
            ctx: Execution context

        Returns:
            TaskResult with status and output information
        """
        pass

    @abstractmethod
    def validate(self, result: TaskResult, ctx: ExecutorContext) -> bool:
        """Validate the execution result.

        Args:
            result: TaskResult to validate
            ctx: Execution context

        Returns:
            True if validation passed
        """
        pass

    @abstractmethod
    def cleanup(self, task: Any, ctx: ExecutorContext) -> None:
        """Clean up after task execution.

        Args:
            task: Task that was executed
            ctx: Execution context
        """
        pass

    def run(self, task: Any, ctx: ExecutorContext) -> TaskResult:
        """Run the full execution pipeline.

        This method orchestrates prepare, execute, validate, and cleanup.

        Args:
            task: Task to run
            ctx: Execution context

        Returns:
            TaskResult with status and output information
        """
        try:
            self.prepare(task, ctx)
            result = self.execute(task, ctx)

            if result.is_success:
                valid = self.validate(result, ctx)
                if not valid:
                    result.status = TaskStatus.FAILED
                    result.add_error("Validation failed")

            return result
        finally:
            self.cleanup(task, ctx)
