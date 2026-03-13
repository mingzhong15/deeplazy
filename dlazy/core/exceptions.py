"""统一异常类 - 工作流异常体系"""

from __future__ import annotations

import traceback
from enum import Enum
from typing import Any, Dict, Optional


class FailureType(Enum):
    """失败类型枚举"""

    SUBMIT_FAILED = "submit_failed"
    SLURM_FAILED = "slurm_failed"
    CALC_ERROR = "calc_error"
    NODE_ERROR = "node_error"
    SECURITY_ERROR = "security_error"
    RESOURCE_ERROR = "resource_error"
    TRANSFORM_ERROR = "transform_error"
    INFER_ERROR = "infer_error"
    CONFIG_ERROR = "config_error"


class WorkflowError(Exception):
    """工作流基础异常"""

    failure_type: FailureType = FailureType.CALC_ERROR

    def __init__(
        self,
        message: str,
        *,
        stage: Optional[str] = None,
        task_path: Optional[str] = None,
        original_exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.task_path = task_path
        self.original_exception = original_exception
        self.context = context or {}
        self.traceback_str: Optional[str] = None
        if original_exception:
            self.traceback_str = traceback.format_exc()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化"""
        return {
            "error_type": self.__class__.__name__,
            "failure_type": self.failure_type.value,
            "message": self.message,
            "stage": self.stage,
            "task_path": self.task_path,
            "context": self.context,
            "traceback": self.traceback_str,
        }

    def __str__(self) -> str:
        parts = [self.message]
        if self.stage:
            parts.insert(0, f"[{self.stage}]")
        if self.task_path:
            parts.append(f"(task: {self.task_path})")
        return " ".join(parts)


class ConfigError(WorkflowError):
    """配置错误"""

    failure_type = FailureType.CONFIG_ERROR


class NodeError(WorkflowError):
    """节点错误，需要重算"""

    failure_type = FailureType.NODE_ERROR


class CalculationError(WorkflowError):
    """计算错误"""

    failure_type = FailureType.CALC_ERROR


class TransformError(WorkflowError):
    """格式转换错误"""

    failure_type = FailureType.TRANSFORM_ERROR


class InferError(WorkflowError):
    """推理错误"""

    failure_type = FailureType.INFER_ERROR


class SecurityError(WorkflowError):
    """安全相关错误"""

    failure_type = FailureType.SECURITY_ERROR


class ResourceError(WorkflowError):
    """资源管理错误"""

    failure_type = FailureType.RESOURCE_ERROR


class GroupNotFoundError(WorkflowError):
    """组不存在"""

    failure_type = FailureType.CALC_ERROR


class HamiltonianNotFoundError(WorkflowError):
    """哈密顿量文件缺失"""

    failure_type = FailureType.CALC_ERROR


class AbortException(WorkflowError):
    """快速失败异常，触发工作流中断"""

    failure_type = FailureType.CALC_ERROR

    def __init__(
        self,
        reason: str,
        error_details: Optional[Dict[str, Any]] = None,
        *,
        stage: Optional[str] = None,
        task_path: Optional[str] = None,
    ):
        super().__init__(
            reason,
            stage=stage,
            task_path=task_path,
            context=error_details,
        )
        self.reason = reason
        self.error_details = error_details or {}
