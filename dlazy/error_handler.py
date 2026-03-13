"""Unified error handling module for batch workflow."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .record_utils import ErrorTask, append_error_task

if TYPE_CHECKING:
    from .path_resolver import BatchPathResolver


@dataclass
class ErrorContext:
    """Error context for recording failed tasks.

    Attributes:
        path: Task path.
        stage: Stage name (olp/infer/calc).
        error: Error message.
        batch_index: Batch index.
        task_id: Task ID.
        resolver: Path resolver for getting error file path.
    """

    path: str
    stage: str
    error: str
    batch_index: int
    task_id: str
    resolver: "BatchPathResolver"


def record_error(ctx: ErrorContext) -> None:
    """Record an error task to the appropriate error file.

    Creates an ErrorTask and appends it to the stage-specific error_tasks.jsonl file.

    Args:
        ctx: Error context containing all necessary information.
    """
    error_task = ErrorTask(
        path=ctx.path,
        stage=ctx.stage,
        error=ctx.error,
        batch_id=str(ctx.batch_index),
        task_id=ctx.task_id,
        retry_count=0,
    )

    if ctx.stage == "olp":
        error_file = ctx.resolver.get_olp_error_file()
    elif ctx.stage == "infer":
        error_file = ctx.resolver.get_infer_error_file()
    elif ctx.stage == "calc":
        error_file = ctx.resolver.get_calc_error_file()
    else:
        raise ValueError(f"Unknown stage: {ctx.stage}")

    append_error_task(error_file, error_task)
