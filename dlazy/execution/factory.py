"""Executor factory for creating stage-specific executors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from dlazy.execution.base import Executor
from dlazy.execution.olp_executor import OlpExecutor
from dlazy.execution.infer_executor import InferExecutor
from dlazy.execution.calc_executor import CalcExecutor

if TYPE_CHECKING:
    from dlazy.scheduler.job_manager import JobManager


def create_executor(
    stage: str,
    config: Optional[Dict[str, Any]] = None,
    job_manager: Optional["JobManager"] = None,
) -> Executor:
    """Create an executor for the specified stage.

    Args:
        stage: Stage name (olp, infer, calc)
        config: Configuration dictionary with command templates
        job_manager: Optional JobManager for SLURM submission

    Returns:
        Executor instance for the stage

    Raises:
        ValueError: If stage is not recognized
    """
    config = config or {}

    if stage == "olp":
        commands = config.get("commands", {})
        return OlpExecutor(
            job_manager=job_manager,
            openmx_command=commands.get("run_openmx", "openmx"),
            extract_command=commands.get("extract_overlap"),
            num_cores=config.get("num_cores", 24),
            max_processes=config.get("max_processes", 1),
            node_error_flag=config.get("node_error_flag"),
        )

    elif stage == "infer":
        commands = config.get("commands", {})
        return InferExecutor(
            job_manager=job_manager,
            transform_command=commands.get("transform", "transform"),
            infer_command=commands.get("infer", "infer"),
            transform_reverse_command=commands.get(
                "transform_reverse", "transform_reverse"
            ),
            num_groups=config.get("num_groups", 1),
        )

    elif stage == "calc":
        commands = config.get("commands", {})
        return CalcExecutor(
            job_manager=job_manager,
            openmx_command=commands.get("run_openmx", "openmx"),
            num_cores=config.get("num_cores", 24),
            max_processes=config.get("max_processes", 1),
            node_error_flag=config.get("node_error_flag"),
        )

    else:
        raise ValueError(f"Unknown stage: {stage}. Expected one of: olp, infer, calc")


def get_executor_class(stage: str) -> type:
    """Get the executor class for a stage.

    Args:
        stage: Stage name (olp, infer, calc)

    Returns:
        Executor class

    Raises:
        ValueError: If stage is not recognized
    """
    stage_map = {
        "olp": OlpExecutor,
        "infer": InferExecutor,
        "calc": CalcExecutor,
    }

    if stage not in stage_map:
        raise ValueError(f"Unknown stage: {stage}. Expected one of: olp, infer, calc")

    return stage_map[stage]


__all__ = [
    "create_executor",
    "get_executor_class",
]
