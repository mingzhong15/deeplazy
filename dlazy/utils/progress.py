"""Progress tracking utilities using Rich library."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict

from rich.progress import Progress, TaskID, BarColumn, TextColumn, TimeElapsedColumn
from rich.console import Console


@dataclass
class TaskProgress:
    """Track progress for a single task or batch.

    Attributes:
        total: Total number of items to process
        completed: Number of items completed
        description: Description of the task
    """

    total: int
    completed: int = 0
    description: str = "Processing"
    _task_id: Optional[TaskID] = field(default=None, repr=False)

    def update(self, n: int = 1) -> None:
        """Increment completed count.

        Args:
            n: Number of items to add (default: 1)
        """
        self.completed += n

    def complete(self) -> None:
        """Mark as complete by setting completed to total."""
        self.completed = self.total

    @property
    def percentage(self) -> float:
        """Return completion percentage."""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100

    @property
    def remaining(self) -> int:
        """Return number of remaining items."""
        return max(0, self.total - self.completed)

    @property
    def is_complete(self) -> bool:
        """Check if task is complete."""
        return self.completed >= self.total


class BatchProgress:
    """Track progress for a batch workflow with multiple stages.

    This class provides a context manager interface for displaying
    progress bars for multi-stage workflows.

    Example:
        with BatchProgress() as bp:
            bp.add_stage("OLP", total=100)
            for i in range(100):
                bp.update_stage("OLP")
            bp.complete_stage("OLP")
    """

    def __init__(self, console: Optional[Console] = None):
        """Initialize BatchProgress.

        Args:
            console: Rich console to use (creates new one if None)
        """
        self.console = console or Console()
        self._progress: Optional[Progress] = None
        self._tasks: Dict[str, TaskID] = {}

    def start(self) -> "BatchProgress":
        """Start the progress display."""
        self._progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._progress.start()
        return self

    def add_stage(self, stage: str, total: int) -> TaskID:
        """Add a stage to track.

        Args:
            stage: Name of the stage
            total: Total number of items in this stage

        Returns:
            TaskID for the stage
        """
        if self._progress is None:
            raise RuntimeError("Progress not started. Use start() or context manager.")

        task_id = self._progress.add_task(stage, total=total)
        self._tasks[stage] = task_id
        return task_id

    def update_stage(self, stage: str, n: int = 1) -> None:
        """Update stage progress.

        Args:
            stage: Name of the stage
            n: Number of items to advance (default: 1)
        """
        if self._progress is None:
            return

        task_id = self._tasks.get(stage)
        if task_id is not None:
            self._progress.update(task_id, advance=n)

    def complete_stage(self, stage: str) -> None:
        """Mark a stage as complete.

        Args:
            stage: Name of the stage
        """
        if self._progress is None:
            return

        task_id = self._tasks.get(stage)
        if task_id is not None:
            self._progress.update(
                task_id, completed=self._progress.tasks[task_id].total
            )

    def stop(self) -> None:
        """Stop the progress display."""
        if self._progress is not None:
            self._progress.stop()
            self._progress = None

    def __enter__(self) -> "BatchProgress":
        """Enter context manager."""
        return self.start()

    def __exit__(self, *args) -> None:
        """Exit context manager."""
        self.stop()


def create_progress_bar(
    description: str = "Processing",
    total: int = 100,
    console: Optional[Console] = None,
) -> tuple:
    """Create a simple progress bar.

    Args:
        description: Description for the progress bar
        total: Total number of items
        console: Rich console to use

    Returns:
        Tuple of (Progress, TaskID)
    """
    progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )
    task_id = progress.add_task(description, total=total)
    return progress, task_id
