"""自定义异常类"""

from enum import Enum
from typing import Any, Dict, Optional


class FailureType(Enum):
    """失败类型枚举"""

    SUBMIT_FAILED = "submit_failed"
    SLURM_FAILED = "slurm_failed"
    CALC_ERROR = "calc_error"
    NODE_ERROR = "node_error"


class WorkflowError(Exception):
    """工作流基础异常"""

    pass


class ConfigError(WorkflowError):
    """配置错误"""

    pass


class NodeError(WorkflowError):
    """节点错误，需要重算"""

    pass


class CalculationError(WorkflowError):
    """计算错误"""

    pass


class TransformError(WorkflowError):
    """格式转换错误"""

    pass


class InferError(WorkflowError):
    """推理错误"""

    pass


class GroupNotFoundError(WorkflowError):
    """组不存在"""

    pass


class HamiltonianNotFoundError(WorkflowError):
    """哈密顿量文件缺失"""

    pass


class AbortException(Exception):
    """快速失败异常，触发工作流中断"""

    def __init__(self, reason: str, error_details: Optional[Dict[str, Any]] = None):
        self.reason = reason
        self.error_details = error_details
        super().__init__(reason)
