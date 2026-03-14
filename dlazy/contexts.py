"""执行上下文定义 - 替代全局变量"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .core.workflow_state import JobMonitor


@dataclass
class BaseContext:
    """基础上下文"""

    config: Dict[str, Any]
    workflow_root: Path
    workdir: Path


@dataclass
class BatchContext:
    """Batch workflow context."""

    config_path: Path
    workflow_root: Path
    batch_size: int
    fresh: bool = False
    state_file: Optional[Path] = None
    olp_tasks_file: Optional[Path] = None
    infer_tasks_file: Optional[Path] = None
    calc_tasks_file: Optional[Path] = None
    error_tasks_file: Optional[Path] = None
    monitor: Optional[JobMonitor] = None

    def __post_init__(self):
        if self.batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {self.batch_size}")


@dataclass
class OLPContext(BaseContext):
    """OLP阶段上下文"""

    result_dir: Path
    progress_file: Path
    folders_file: Path
    error_file: Path
    num_cores: int
    max_processes: int
    node_error_flag: Optional[Path] = None
    stru_log: Optional[Path] = None
    monitor: Optional[JobMonitor] = None

    def __post_init__(self):
        if self.num_cores <= 0:
            raise ValueError(f"num_cores must be positive, got {self.num_cores}")
        if self.max_processes <= 0:
            raise ValueError(
                f"max_processes must be positive, got {self.max_processes}"
            )


@dataclass
class InferContext(BaseContext):
    """Infer阶段上下文"""

    result_dir: Path
    error_file: Path
    hamlog_file: Path
    group_info_file: Path
    num_groups: int
    random_seed: int
    parallel: int
    model_dir: Path
    dataset_prefix: str
    monitor: Optional[JobMonitor] = None

    def __post_init__(self):
        if self.num_groups <= 0:
            raise ValueError(f"num_groups must be positive, got {self.num_groups}")
        if self.parallel <= 0:
            raise ValueError(f"parallel must be positive, got {self.parallel}")
        if not self.model_dir.exists():
            raise ValueError(f"model_dir does not exist: {self.model_dir}")


@dataclass
class CalcContext(BaseContext):
    """Calc阶段上下文"""

    result_dir: Path
    progress_file: Path
    folders_file: Path
    error_file: Path
    hamlog_file: Path
    monitor: Optional[JobMonitor] = None
