"""自定义异常类"""


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
