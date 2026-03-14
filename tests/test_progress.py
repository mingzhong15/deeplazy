"""Tests for progress utilities."""

import pytest
from unittest.mock import MagicMock, patch

from dlazy.utils.progress import TaskProgress, BatchProgress, create_progress_bar


def test_task_progress_initialization():
    """Test TaskProgress initialization."""
    progress = TaskProgress(total=100)

    assert progress.total == 100
    assert progress.completed == 0
    assert progress.description == "Processing"


def test_task_progress_update():
    """Test TaskProgress update method."""
    progress = TaskProgress(total=100)
    progress.update(50)

    assert progress.completed == 50
    assert progress.percentage == 50.0


def test_task_progress_complete():
    """Test TaskProgress complete method."""
    progress = TaskProgress(total=100)
    progress.complete()

    assert progress.completed == 100
    assert progress.percentage == 100.0
    assert progress.is_complete is True


def test_task_progress_zero_total():
    """Test TaskProgress with zero total."""
    progress = TaskProgress(total=0)

    assert progress.percentage == 0.0
    assert progress.remaining == 0


def test_task_progress_remaining():
    """Test TaskProgress remaining property."""
    progress = TaskProgress(total=100)
    progress.update(30)

    assert progress.remaining == 70


def test_task_progress_is_complete():
    """Test TaskProgress is_complete property."""
    progress = TaskProgress(total=100)

    assert progress.is_complete is False

    progress.update(100)
    assert progress.is_complete is True

    # Over-complete is also complete
    progress.update(10)
    assert progress.is_complete is True


def test_batch_progress_context_manager():
    """Test BatchProgress context manager."""
    with BatchProgress() as bp:
        bp.add_stage("test", 10)
        bp.update_stage("test", 5)
        bp.complete_stage("test")


def test_batch_progress_add_stage():
    """Test BatchProgress add_stage method."""
    bp = BatchProgress()
    bp.start()

    task_id = bp.add_stage("OLP", 100)

    assert task_id is not None
    assert "OLP" in bp._tasks

    bp.stop()


def test_batch_progress_update_stage():
    """Test BatchProgress update_stage method."""
    bp = BatchProgress()
    bp.start()
    bp.add_stage("test", 100)

    # Should not raise
    bp.update_stage("test", 10)

    bp.stop()


def test_batch_progress_complete_stage():
    """Test BatchProgress complete_stage method."""
    bp = BatchProgress()
    bp.start()
    bp.add_stage("test", 100)
    bp.update_stage("test", 50)

    bp.complete_stage("test")

    bp.stop()


def test_batch_progress_not_started():
    """Test BatchProgress raises error if not started."""
    bp = BatchProgress()

    with pytest.raises(RuntimeError):
        bp.add_stage("test", 100)


def test_create_progress_bar():
    """Test create_progress_bar factory function."""
    progress, task_id = create_progress_bar("Test", 100)

    assert progress is not None
    assert task_id is not None


def test_create_progress_bar_with_console():
    """Test create_progress_bar with custom console."""
    from rich.console import Console

    console = Console()
    progress, task_id = create_progress_bar("Test", 100, console=console)

    assert progress is not None
