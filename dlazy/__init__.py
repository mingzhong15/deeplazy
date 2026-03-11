"""工作流核心库"""

from .executor import WorkflowExecutor
from .contexts import OLPContext, InferContext, CalcContext, BatchContext
from .exceptions import (
    WorkflowError,
    ConfigError,
    NodeError,
    CalculationError,
    TransformError,
    InferError,
    GroupNotFoundError,
    HamiltonianNotFoundError,
    FailureType,
    AbortException,
)

__version__ = "2.4.0"
__all__ = [
    "WorkflowExecutor",
    "OLPContext",
    "InferContext",
    "CalcContext",
    "BatchContext",
    "WorkflowError",
    "ConfigError",
    "NodeError",
    "CalculationError",
    "TransformError",
    "InferError",
    "GroupNotFoundError",
    "HamiltonianNotFoundError",
    "FailureType",
    "AbortException",
]
