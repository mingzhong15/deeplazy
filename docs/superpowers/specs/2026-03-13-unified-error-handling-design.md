# 错误处理统一修复方案

**日期**: 2026-03-13
**状态**: 设计阶段
**作者**: AI Assistant

---

## 概述

本方案旨在解决 deeplazy 项目中分散、不一致的错误处理问题，通过渐进式重构建立统一的错误处理体系。

---

## 发现的问题

### 1. Calc 阶段异常吞没 (严重)
- **位置**: `commands.py:1005-1020`
- **问题**: 捕获所有异常后只返回 `("failed", label)`，不重新抛出
- **影响**: 上层无法感知具体错误类型，调试困难

### 2. 双重错误记录不同步 (中等)
- **系统1**: `ErrorTask` → `error_tasks.jsonl` (`error_handler.py`)
- **系统2**: `TaskError` → `monitor_state.json` (`monitor.py`)
- **问题**: 两套系统独立运行，数据不同步

### 3. 重试计数分散 (轻微)
- **位置**: `constants.py` + `workflow.py` + `monitor.py`
- **问题**: 三处各自维护重试计数，逻辑不一致

### 4. 异常继承关系混乱
- **问题**: `AbortException` 没有继承自 `WorkflowError`
- **问题**: `FailureType` 枚举与异常类没有直接映射

### 5. 错误上下文链丢失
- **问题**: 异常重新抛出时丢失原始堆栈信息

---

## 设计约束

1. **向后兼容性**: 可以迁移，新格式可优化
2. **重试范围**: 支持任务级 + 阶段级 + 跨批次三层重试
3. **迁移策略**: 渐进式重构，新旧系统可并存

---

## 解决方案

### 第一部分：新的异常体系

#### 设计目标

1. `AbortException` 继承自 `WorkflowError`
2. 每个异常类关联 `FailureType`
3. 异常保留原始堆栈信息

#### 新增 FailureType

```python
class FailureType(Enum):
    """失败类型枚举"""
    SUBMIT_FAILED = "submit_failed"
    SLURM_FAILED = "slurm_failed"
    CALC_ERROR = "calc_error"
    NODE_ERROR = "node_error"
    CONFIG_ERROR = "config_error"       # 新增
    TRANSFORM_ERROR = "transform_error" # 新增
    INFER_ERROR = "infer_error"         # 新增
    UNKNOWN_ERROR = "unknown_error"     # 新增
```

#### 重构 WorkflowError 基类

```python
class WorkflowError(Exception):
    """工作流基础异常"""

    failure_type: FailureType = FailureType.UNKNOWN_ERROR

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
        self.traceback_str = traceback.format_exc() if original_exception else None

    def get_full_context(self) -> Dict[str, Any]:
        """获取完整错误上下文"""
        return {
            "type": self.__class__.__name__,
            "failure_type": self.failure_type.value,
            "message": self.message,
            "stage": self.stage,
            "task_path": self.task_path,
            "context": self.context,
            "original_exception": str(self.original_exception) if self.original_exception else None,
            "traceback": self.traceback_str,
        }
```

#### 异常类与 FailureType 映射

| 异常类 | FailureType |
|--------|-------------|
| `SubmitFailedError` (新增) | SUBMIT_FAILED |
| `SlurmFailedError` (新增) | SLURM_FAILED |
| `CalculationError` | CALC_ERROR |
| `NodeError` | NODE_ERROR |
| `ConfigError` | CONFIG_ERROR |
| `TransformError` | TRANSFORM_ERROR |
| `InferError` | INFER_ERROR |
| `WorkflowError` | UNKNOWN_ERROR |

#### AbortException 重构

```python
class AbortException(WorkflowError):
    """快速失败异常，触发工作流中断"""

    failure_type = FailureType.UNKNOWN_ERROR

    def __init__(
        self,
        reason: str,
        *,
        error_details: Optional[Dict[str, Any]] = None,
        stage: Optional[str] = None,
        task_path: Optional[str] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(
            message=reason,
            stage=stage,
            task_path=task_path,
            original_exception=original_exception,
            context=error_details or {},
        )
        self.reason = reason
        self.error_details = error_details
```

#### 辅助函数

```python
def exception_to_failure_type(exc: Exception) -> FailureType:
    """将异常映射到 FailureType"""
    if isinstance(exc, WorkflowError):
        return exc.failure_type
    return FailureType.UNKNOWN_ERROR


def wrap_exception(
    exc: Exception,
    *,
    stage: Optional[str] = None,
    task_path: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> WorkflowError:
    """将任意异常包装为 WorkflowError，保留原始堆栈"""
    if isinstance(exc, WorkflowError):
        if stage and not exc.stage:
            exc.stage = stage
        if task_path and not exc.task_path:
            exc.task_path = task_path
        if context:
            exc.context.update(context)
        return exc

    failure_type = exception_to_failure_type(exc)
    error_class = FAILURE_TYPE_TO_ERROR.get(failure_type, WorkflowError)
    
    return error_class(
        message=str(exc),
        stage=stage,
        task_path=task_path,
        original_exception=exc,
        context=context,
    )
```

---

### 第二部分：统一错误处理中心

#### 设计目标

1. 合并 `ErrorTask` 和 `TaskError` 两套系统
2. 统一的错误记录和通知接口
3. 兼容旧文件格式

#### 统一错误记录格式

```python
@dataclass
class ErrorRecord:
    """统一的错误记录格式"""

    path: str
    stage: str
    error_type: str                    # 异常类名
    failure_type: FailureType          # 失败类型枚举
    message: str
    timestamp: datetime
    batch_id: Optional[str] = None
    task_id: Optional[str] = None
    retry_count: int = 0
    traceback: Optional[str] = None    # 原始堆栈
    context: Dict[str, Any] = field(default_factory=dict)
```

#### ErrorHandler 类

```python
class ErrorHandler:
    """统一错误处理中心"""

    def __init__(
        self,
        workflow_root: Path,
        resolver: Optional["BatchPathResolver"] = None,
    ):
        self.workflow_root = workflow_root
        self.resolver = resolver
        self.errors: List[ErrorRecord] = []
        self._error_file_cache: Dict[str, Path] = {}

    def record_error(
        self,
        error: Exception,
        *,
        stage: str,
        task_path: Optional[str] = None,
        batch_id: Optional[str] = None,
        task_id: Optional[str] = None,
        retry_count: int = 0,
    ) -> ErrorRecord:
        """记录错误（核心接口）"""
        # 自动包装异常
        # 写入文件
        # 返回记录

    def get_errors_by_stage(self, stage: str) -> List[ErrorRecord]:
        """获取指定阶段的所有错误"""

    def get_errors_by_path(self, path: str) -> List[ErrorRecord]:
        """获取指定路径的所有错误"""

    def get_retry_count(self, path: str, stage: str) -> int:
        """获取任务的累计重试次数"""

    def should_abort(
        self,
        failure_type: FailureType,
        max_retries: Dict[FailureType, int],
    ) -> bool:
        """判断是否应该中断工作流"""

    def to_monitor_state(self) -> Dict[str, Any]:
        """导出为 monitor_state.json 格式（兼容旧系统）"""

    def load_from_monitor_state(self, state: Dict[str, Any]) -> None:
        """从 monitor_state.json 格式加载"""
```

---

### 第三部分：统一重试策略

#### 设计目标

1. 集中管理重试配置
2. 支持三层重试：任务级、阶段级、跨批次
3. 统一重试决策逻辑

#### RetryLevel 枚举

```python
class RetryLevel(Enum):
    """重试级别"""
    TASK = "task"           # 单任务重试
    STAGE = "stage"         # 阶段重试
    CROSS_BATCH = "cross_batch"  # 跨批次重试
```

#### RetryConfig 类

```python
@dataclass
class RetryConfig:
    """统一重试配置"""

    task_max_retries: Dict[FailureType, int] = field(default_factory=lambda: {
        FailureType.SUBMIT_FAILED: 0,
        FailureType.SLURM_FAILED: 3,
        FailureType.NODE_ERROR: 3,
        FailureType.CALC_ERROR: -1,  # -1 表示无限制
    })

    stage_max_retries: int = 3

    cross_batch_max_retries: int = 3

    def get_max_retries(self, level: RetryLevel, failure_type: Optional[FailureType] = None) -> int:
        """获取指定级别和失败类型的最大重试次数"""
```

#### RetryManager 类

```python
class RetryManager:
    """重试管理器 - 三层重试统一管理"""

    def __init__(
        self,
        config: RetryConfig,
        error_handler: "ErrorHandler",
    ):
        self.config = config
        self.error_handler = error_handler

        self.task_retry_counts: Dict[str, int] = {}      # "stage:path" -> count
        self.stage_retry_counts: Dict[str, int] = {}     # "stage" -> count
        self.cross_batch_retry_count: int = 0

    def should_retry_task(self, path: str, stage: str, failure_type: FailureType) -> bool:
        """判断任务是否应该重试"""

    def should_retry_stage(self, stage: str) -> bool:
        """判断阶段是否应该重试"""

    def should_retry_cross_batch(self) -> bool:
        """判断是否应该跨批次重试"""

    def record_task_failure(self, path: str, stage: str, failure_type: FailureType) -> None:
        """记录任务失败"""

    def record_stage_failure(self, stage: str) -> None:
        """记录阶段失败"""

    def record_cross_batch_failure(self) -> None:
        """记录跨批次失败"""

    def should_abort_workflow(self) -> bool:
        """判断是否应该中断工作流"""
```

---

### 第四部分：具体代码修改

#### 4.1 修复 commands.py 异常吞没

**修改前**:
```python
except Exception as e:
    logger.error("Calc failed: %s", e)
    write_progress("error")
    # ... 记录错误 ...
    return ("failed", label)  # 吞没异常！
```

**修改后**:
```python
from .exceptions import wrap_exception, WorkflowError

try:
    # ... calc logic ...
    return ("success", label)

except Exception as e:
    logger.error("Calc failed: %s", e)
    write_progress("error")

    workflow_error = wrap_exception(
        e,
        stage="calc",
        task_path=task.path,
        context={"batch_index": resolver.batch_index},
    )

    if self.error_handler:
        self.error_handler.record_error(
            workflow_error,
            stage="calc",
            task_path=task.path,
            batch_id=str(resolver.batch_index),
            task_id=f"{task_index:06d}",
        )

    raise workflow_error  # 重新抛出，保留上下文！
```

#### 4.2 更新 error_handler.py

保留旧接口作为兼容层，内部委托给新的 `ErrorHandler`。

#### 4.3 更新 constants.py

移除分散的重试配置，统一使用 `RetryConfig`。

```python
# 废弃常量
# MAX_RETRY_COUNT = 3
# DEFAULT_MAX_RETRIES = {...}

# 使用统一配置
from .retry_config import RetryConfig
```

#### 4.4 更新 workflow.py

```python
from .unified_error_handler import ErrorHandler
from .retry_config import RetryConfig, RetryManager

class WorkflowManager(WorkflowBase):
    def __init__(self, config_path: Path, workdir: Path):
        # 初始化统一错误处理器
        self.error_handler = ErrorHandler(workflow_root=self.workdir)
        
        # 初始化重试管理器
        self.retry_manager = RetryManager(
            RetryConfig.default(),
            self.error_handler,
        )
```

---

### 第五部分：迁移方案

#### 5.1 迁移脚本功能

1. 迁移 `error_tasks.jsonl` 到新格式
2. 迁移 `monitor_state.json` 到新格式
3. 保留原始文件备份

#### 5.2 新旧系统共存

过渡期使用 `ErrorHandlingAdapter`：

```python
class ErrorHandlingAdapter:
    """错误处理适配器 - 过渡期使用"""

    def __init__(
        self,
        workflow_root: Path,
        resolver: Optional["BatchPathResolver"] = None,
        use_new_system: bool = True,
    ):
        self.use_new_system = use_new_system
        # ...
```

#### 5.3 迁移步骤

1. 运行迁移脚本转换历史数据
2. 部署新代码（启用兼容模式）
3. 验证新系统正常工作
4. 切换到新系统
5. 移除旧代码

---

## 实施计划

### 阶段1：基础重构（1-2天）
- [ ] 实现新的异常体系 (`exceptions.py`)
- [ ] 创建 `unified_error_handler.py`
- [ ] 创建 `retry_config.py`
- [ ] 编写单元测试

### 阶段2：渐进迁移（2-3天）
- [ ] 更新 `error_handler.py` 添加兼容层
- [ ] 修复 `commands.py` 异常吞没问题
- [ ] 更新 `workflow.py` 使用新系统
- [ ] 更新 `workflow_base.py`

### 阶段3：迁移和验证（1-2天）
- [ ] 编写迁移脚本
- [ ] 测试迁移脚本
- [ ] 验证新旧系统兼容性
- [ ] 更新文档

### 阶段4：清理（1天）
- [ ] 移除旧代码
- [ ] 删除废弃常量
- [ ] 最终测试

---

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `dlazy/exceptions.py` | 重构 | 新异常体系 |
| `dlazy/unified_error_handler.py` | 新建 | 统一错误处理中心 |
| `dlazy/retry_config.py` | 新建 | 统一重试策略 |
| `dlazy/error_handler.py` | 重构 | 兼容层 |
| `dlazy/commands.py` | 修改 | 修复异常吞没 |
| `dlazy/workflow.py` | 修改 | 使用新系统 |
| `dlazy/workflow_base.py` | 修改 | 使用新系统 |
| `dlazy/constants.py` | 修改 | 移除废弃常量 |
| `dlazy/monitor.py` | 废弃 | 功能合并到新系统 |
| `scripts/migrate_errors.py` | 新建 | 迁移脚本 |

---

## 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 迁移脚本丢失数据 | 低 | 高 | 备份原始文件 |
| 新系统引入bug | 中 | 高 | 完整单元测试 |
| 兼容性问题 | 中 | 中 | 过渡期适配器 |
| 性能影响 | 低 | 低 | 异步写入 |

---

## 成功标准

1. 所有异常正确传递，无吞没
2. 错误记录统一，数据一致
3. 重试逻辑集中在 `RetryManager`
4. 异常继承关系清晰
5. 错误上下文完整保留
6. 历史数据成功迁移
7. 所有测试通过
