"""执行上下文定义 - 替代全局变量"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List


@dataclass
class BaseContext:
    """基础上下文"""

    config: Dict[str, Any]
    workflow_root: Path
    workdir: Path


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


@dataclass
class CalcContext(BaseContext):
    """Calc阶段上下文"""

    result_dir: Path
    progress_file: Path
    folders_file: Path
    error_file: Path
    hamlog_file: Path
