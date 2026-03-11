# JobMonitor 模块设计文档

## 概述

新增独立监控模块 `monitor.py`，统一管理作业状态监控、错误处理、重试决策和快速失败。

## 背景

当前系统存在的问题：
1. **单任务失败不中断batch** - `pool.map` 继续执行剩余任务
2. **整个batch重试** - 任何任务失败导致整个stage重试
3. **无细粒度错误隔离** - 没有区分不同失败类型的处理策略

## 设计目标

1. 区分不同失败类型，采用不同处理策略
2. 支持快速失败机制
3. 支持断点续传（阶段粒度）
4. 统一的监控和日志管理

## 架构

### 模块关系

```
┌─────────────────┐
│ WorkflowManager │ ──提交作业──→ ┌─────────────┐
│  (workflow.py)  │ ←─状态查询── │             │
└─────────────────┘               │  JobMonitor │
                                  │  (monitor.py)│
┌─────────────────┐               │             │
│   Executor      │ ──报告错误──→ └─────────────┘
│ (executor.py)   │ ←─失败决策──
└─────────────────┘
```

### 文件结构

```
deeplazy/
├── monitor.py           # 新增：JobMonitor 主模块
├── exceptions.py        # 修改：添加 FailureType, AbortException
├── workflow.py          # 修改：集成 JobMonitor
├── executor.py          # 修改：报告错误到 Monitor
├── contexts.py          # 修改：添加 monitor 字段
├── constants.py         # 修改：添加 Monitor 相关常量
└── ...
```

## 核心组件

### 1. FailureType 枚举

```python
class FailureType(Enum):
    SUBMIT_FAILED = "submit_failed"      # 任务提交失败
    SLURM_FAILED = "slurm_failed"        # Slurm作业失败
    CALC_ERROR = "calc_error"            # 计算错误
    NODE_ERROR = "node_error"            # 节点错误
```

### 2. EventType 枚举

```python
class EventType(Enum):
    JOB_SUBMITTED = "job_submitted"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    ERROR_REPORTED = "error_reported"
    RETRY_TRIGGERED = "retry_triggered"
    ABORT_TRIGGERED = "abort_triggered"
```

### 3. 数据结构

```python
@dataclass
class MonitorConfig:
    max_retries: Dict[FailureType, int]

@dataclass
class MonitorState:
    job_id: Optional[str]
    retry_counts: Dict[FailureType, int]
    abort_flag: bool
    abort_reason: Optional[str]
    errors: List[TaskError]
    
    def to_dict(self) -> Dict: ...
    @classmethod
    def from_dict(cls, data: Dict) -> "MonitorState": ...

@dataclass
class TaskError:
    stage: str
    failure_type: FailureType
    message: str
    timestamp: datetime

@dataclass
class MonitorEvent:
    timestamp: datetime
    event_type: EventType
    stage: str
    job_id: Optional[str]
    message: str
    details: Optional[Dict]

@dataclass
class RestoreInfo:
    completed: Set[str]
    failed: List[Tuple[str, str]]
```

### 4. AbortException

```python
class AbortException(Exception):
    """快速失败异常，触发工作流中断"""
    def __init__(self, reason: str, error_details: Optional[Dict] = None):
        self.reason = reason
        self.error_details = error_details
```

### 5. JobMonitor 主类

```python
class JobMonitor:
    """统一作业监控管理器"""
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        self.state = MonitorState()
    
    # === 提交管理 ===
    def submit_job(self, stage: str, submit_fn: Callable) -> SubmitResult:
        """提交作业，处理提交失败"""
    
    # === 状态监控 ===
    def check_job_status(self, job_id: str) -> JobStatus:
        """查询Slurm作业状态"""
    
    # === 错误收集 ===
    def report_error(self, error: TaskError) -> None:
        """报告任务执行错误"""
    
    # === 重试决策 ===
    def should_retry(self, failure_type: FailureType) -> bool:
        """判断是否应该重试"""
    
    def get_retry_count(self, failure_type: FailureType) -> int:
        """获取当前重试次数"""
    
    # === 快速失败 ===
    def should_abort(self) -> bool:
        """是否应该中断工作流"""
    
    def trigger_abort(self, reason: str) -> None:
        """触发快速失败"""
    
    # === 断点续传 ===
    def restore_from_state(self, state_data: Dict) -> None:
        """从状态数据恢复"""
    
    def save_state(self) -> Dict:
        """保存状态数据"""
    
    # === 日志 ===
    def log_event(self, event: MonitorEvent) -> None:
        """记录监控事件"""
```

## 失败处理策略

### 默认配置

```python
DEFAULT_MAX_RETRIES = {
    FailureType.SUBMIT_FAILED: 0,   # 提交失败 → 快速失败
    FailureType.SLURM_FAILED: 3,    # Slurm失败 → 重试3次
    FailureType.NODE_ERROR: 3,      # 节点错误 → 重试3次
    FailureType.CALC_ERROR: -1,     # 计算错误 → 无限记录（不中断）
}
```

### 决策流程

```
任务执行出错
    │
    ├─ CALC_ERROR? ─────────────────→ 记录日志，继续
    │
    ├─ SUBMIT_FAILED? ──────────────→ 记录日志，快速失败
    │
    └─ 其他 (SLURM_FAILED/NODE_ERROR)?
           │
           ├─ retry_count < max_retries? ─→ 重试
           │
           └─ retry_count >= max_retries? ─→ 快速失败
```

### should_abort() 实现

```python
def should_abort(self) -> bool:
    if self.state.abort_flag:
        return True
    
    for ftype, max_retry in self.config.max_retries.items():
        if max_retry == 0:  # 快速失败类型
            if self.state.retry_counts.get(ftype, 0) > 0:
                return True
        elif max_retry > 0:  # 有限重试类型
            if self.state.retry_counts.get(ftype, 0) >= max_retry:
                return True
    
    return False
```

## 断点续传

### 阶段粒度断点续传

- 以阶段为最小单位
- 重启时跳过已完成的阶段
- 当前阶段从头重新执行（覆盖）
- 输入来自上一个成功阶段的输出

### 示例

```
执行过程：
  0olp  ──完成──→ 1infer ──执行一半出错──→ 中断
  
重启后：
  读取 state.json → 0olp 已完成，1infer 失败
  跳过 0olp
  重新执行 1infer（使用 0olp/folders.dat 作为输入）
```

### state.json 结构

```json
{
  "current_stage": "1infer",
  "stages": {
    "0olp": {"status": "completed", "end_time": "..."},
    "1infer": {
      "status": "failed",
      "retry_count": 1,
      "last_error": "node_error",
      "start_time": "..."
    },
    "2calc": {"status": "pending"}
  },
  "monitor": {
    "retry_counts": {"node_error": 1},
    "abort_flag": true,
    "abort_reason": "节点错误超过重试上限"
  }
}
```

## 模块集成

### WorkflowManager 改造

```python
class WorkflowManager:
    def __init__(self, config_path: Path, workdir: Path):
        # ... 现有代码 ...
        self.monitor = JobMonitor(MonitorConfig(
            max_retries=DEFAULT_MAX_RETRIES
        ))
    
    def _submit_job(self, stage_name: str) -> Optional[str]:
        result = self.monitor.submit_job(stage_name, self._do_submit)
        if not result.success:
            return None
        return result.job_id
    
    def run(self, daemon: bool = False):
        # 循环中检查 abort
        if self.monitor.should_abort():
            logger.error(f"快速失败: {self.monitor.state.abort_reason}")
            break
```

### Executor 改造

```python
class WorkflowExecutor:
    @staticmethod
    def run_olp_stage(..., monitor: JobMonitor = None):
        for record in records:
            result = execute_func(record)
            
            if result[0] in ["failed", "node_error"]:
                monitor.report_error(TaskError(
                    stage="0olp",
                    failure_type=FailureType.NODE_ERROR if result[0] == "node_error" 
                                 else FailureType.CALC_ERROR,
                    message=result[1],
                    timestamp=datetime.now()
                ))
            
            if monitor and monitor.should_abort():
                raise AbortException(monitor.state.abort_reason)
```

### Context 改造

在 OLPContext, InferContext, CalcContext 中添加 monitor 字段：

```python
@dataclass
class OLPContext:
    # ... 现有字段 ...
    monitor: Optional[JobMonitor] = None
```

## 日志与事件记录

### 日志文件

```
workdir/
├── workflow.log       # 工作流主日志
├── state.json         # 状态持久化
└── {stage}/
    └── errors.dat     # 该阶段错误详情
```

### 日志输出示例

```
[2024-01-01 10:00:00] INFO: [0olp] 作业提交成功 (job_id: 12345)
[2024-01-01 10:30:00] INFO: [0olp] 检测到节点错误 (label: struct_001)
[2024-01-01 10:30:01] WARN: [0olp] 触发重试 (node_error, 1/3)
[2024-01-01 11:00:00] INFO: [0olp] 计算错误 (label: struct_002, 仅记录)
[2024-01-01 12:00:00] ERROR: [0olp] 节点错误超过重试上限，快速失败
```

## 实施步骤

1. 创建 `monitor.py`，实现 JobMonitor 及相关数据结构
2. 修改 `exceptions.py`，添加 FailureType 和 AbortException
3. 修改 `constants.py`，添加 Monitor 相关常量
4. 修改 `contexts.py`，添加 monitor 字段
5. 修改 `executor.py`，集成错误报告
6. 修改 `workflow.py`，集成 JobMonitor
7. 编写测试用例
8. 更新文档

## 兼容性

- 保持现有 API 兼容
- monitor 参数可选，默认为 None
- 不影响现有工作流的基本功能
