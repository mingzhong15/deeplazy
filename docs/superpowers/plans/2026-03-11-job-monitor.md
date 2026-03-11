# JobMonitor 模块实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现独立监控模块，统一管理作业状态监控、错误处理、重试决策和快速失败。

**Architecture:** 新增 `monitor.py` 作为核心监控模块，通过 `JobMonitor` 类提供统一的监控接口。修改现有模块集成监控功能，保持向后兼容。

**Tech Stack:** Python 3.8+, dataclasses, enum, 标准库

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `deeplazy/monitor.py` | 新建 | JobMonitor 主模块，包含所有监控逻辑 |
| `deeplazy/exceptions.py` | 修改 | 添加 FailureType, AbortException |
| `deeplazy/constants.py` | 修改 | 添加 Monitor 相关常量 |
| `deeplazy/contexts.py` | 修改 | 添加 monitor 字段到各 Context |
| `deeplazy/executor.py` | 修改 | 集成错误报告 |
| `deeplazy/workflow.py` | 修改 | 集成 JobMonitor |
| `tests/test_monitor.py` | 新建 | Monitor 模块测试 |

---

## Chunk 1: 核心数据结构和异常类

### Task 1.1: 添加 FailureType 和 AbortException

**Files:**
- Modify: `deeplazy/exceptions.py`

- [ ] **Step 1: 添加 FailureType 枚举和 AbortException**

```python
# 在文件末尾添加

from enum import Enum


class FailureType(Enum):
    """失败类型枚举"""
    SUBMIT_FAILED = "submit_failed"
    SLURM_FAILED = "slurm_failed"
    CALC_ERROR = "calc_error"
    NODE_ERROR = "node_error"


class AbortException(Exception):
    """快速失败异常，触发工作流中断"""
    def __init__(self, reason: str, error_details: Optional[Dict] = None):
        self.reason = reason
        self.error_details = error_details
        super().__init__(reason)
```

需要在文件顶部添加 `from typing import Dict, Optional`。

- [ ] **Step 2: 验证导入**

Run: `python -c "from deeplazy.exceptions import FailureType, AbortException; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add deeplazy/exceptions.py
git commit -m "feat: add FailureType enum and AbortException"
```

---

### Task 1.2: 添加 Monitor 常量

**Files:**
- Modify: `deeplazy/constants.py`

- [ ] **Step 1: 添加 Monitor 相关常量**

```python
# 在文件末尾添加

# ============================================
# Monitor 配置
# ============================================
from deeplazy.exceptions import FailureType

DEFAULT_MAX_RETRIES = {
    FailureType.SUBMIT_FAILED: 0,
    FailureType.SLURM_FAILED: 3,
    FailureType.NODE_ERROR: 3,
    FailureType.CALC_ERROR: -1,
}

MONITOR_STATE_FILE = "monitor_state.json"
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from deeplazy.constants import DEFAULT_MAX_RETRIES; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add deeplazy/constants.py
git commit -m "feat: add Monitor constants"
```

---

## Chunk 2: Monitor 模块核心实现

### Task 2.1: 创建 Monitor 数据结构

**Files:**
- Create: `deeplazy/monitor.py`

- [ ] **Step 1: 编写 Monitor 数据结构测试**

创建 `tests/test_monitor.py`:

```python
#!/usr/bin/env python3
"""测试 Monitor 模块"""

import pytest
from datetime import datetime
from deeplazy.monitor import (
    MonitorConfig,
    MonitorState,
    TaskError,
    MonitorEvent,
    EventType,
)
from deeplazy.exceptions import FailureType


class TestMonitorConfig:
    def test_default_config(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        assert config.max_retries[FailureType.SUBMIT_FAILED] == 0
        assert config.max_retries[FailureType.SLURM_FAILED] == 3


class TestMonitorState:
    def test_init(self):
        state = MonitorState()
        assert state.job_id is None
        assert state.abort_flag is False
        assert state.retry_counts == {}

    def test_to_dict(self):
        state = MonitorState(job_id="12345", abort_flag=True, abort_reason="test")
        data = state.to_dict()
        assert data["job_id"] == "12345"
        assert data["abort_flag"] is True

    def test_from_dict(self):
        data = {"job_id": "12345", "abort_flag": True, "abort_reason": "test"}
        state = MonitorState.from_dict(data)
        assert state.job_id == "12345"
        assert state.abort_flag is True


class TestTaskError:
    def test_init(self):
        error = TaskError(
            stage="0olp",
            failure_type=FailureType.NODE_ERROR,
            message="test error",
            timestamp=datetime.now(),
        )
        assert error.stage == "0olp"
        assert error.failure_type == FailureType.NODE_ERROR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'deeplazy.monitor'"

- [ ] **Step 3: 实现 Monitor 数据结构**

创建 `deeplazy/monitor.py`:

```python
"""作业监控模块 - 统一管理作业状态监控、错误处理、重试决策"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .exceptions import AbortException, FailureType


class EventType(Enum):
    """监控事件类型"""
    JOB_SUBMITTED = "job_submitted"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    ERROR_REPORTED = "error_reported"
    RETRY_TRIGGERED = "retry_triggered"
    ABORT_TRIGGERED = "abort_triggered"


@dataclass
class MonitorConfig:
    """监控配置"""
    max_retries: Dict[FailureType, int]


@dataclass
class MonitorState:
    """监控状态"""
    job_id: Optional[str] = None
    retry_counts: Dict[FailureType, int] = field(default_factory=dict)
    abort_flag: bool = False
    abort_reason: Optional[str] = None
    errors: List[TaskError] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "retry_counts": {k.value: v for k, v in self.retry_counts.items()},
            "abort_flag": self.abort_flag,
            "abort_reason": self.abort_reason,
            "errors": [e.to_dict() for e in self.errors],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MonitorState":
        retry_counts = {}
        for k, v in data.get("retry_counts", {}).items():
            retry_counts[FailureType(k)] = v

        errors = [TaskError.from_dict(e) for e in data.get("errors", [])]

        return cls(
            job_id=data.get("job_id"),
            retry_counts=retry_counts,
            abort_flag=data.get("abort_flag", False),
            abort_reason=data.get("abort_reason"),
            errors=errors,
        )


@dataclass
class TaskError:
    """任务错误"""
    stage: str
    failure_type: FailureType
    message: str
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "failure_type": self.failure_type.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskError":
        return cls(
            stage=data["stage"],
            failure_type=FailureType(data["failure_type"]),
            message=data["message"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class MonitorEvent:
    """监控事件"""
    timestamp: datetime
    event_type: EventType
    stage: str
    job_id: Optional[str]
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class SubmitResult:
    """提交结果"""
    success: bool
    job_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class JobStatus:
    """作业状态"""
    job_id: str
    state: str  # RUNNING, PENDING, COMPLETED, FAILED, CANCELLED, TIMEOUT
    exit_code: Optional[int] = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add deeplazy/monitor.py tests/test_monitor.py
git commit -m "feat: add Monitor data structures"
```

---

### Task 2.2: 实现 JobMonitor 核心方法

**Files:**
- Modify: `deeplazy/monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: 编写 JobMonitor 核心方法测试**

在 `tests/test_monitor.py` 末尾添加:

```python
class TestJobMonitor:
    def test_init(self):
        from deeplazy.monitor import JobMonitor
        from deeplazy.constants import DEFAULT_MAX_RETRIES

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)
        assert monitor.config.max_retries[FailureType.SUBMIT_FAILED] == 0

    def test_report_error(self):
        from deeplazy.monitor import JobMonitor
        from deeplazy.constants import DEFAULT_MAX_RETRIES

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        error = TaskError(
            stage="0olp",
            failure_type=FailureType.NODE_ERROR,
            message="test error",
            timestamp=datetime.now(),
        )
        monitor.report_error(error)

        assert FailureType.NODE_ERROR in monitor.state.retry_counts
        assert monitor.state.retry_counts[FailureType.NODE_ERROR] == 1

    def test_should_retry(self):
        from deeplazy.monitor import JobMonitor
        from deeplazy.constants import DEFAULT_MAX_RETRIES

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        assert monitor.should_retry(FailureType.NODE_ERROR) is True
        assert monitor.should_retry(FailureType.SUBMIT_FAILED) is False
        assert monitor.should_retry(FailureType.CALC_ERROR) is True

    def test_should_abort_submit_failed(self):
        from deeplazy.monitor import JobMonitor
        from deeplazy.constants import DEFAULT_MAX_RETRIES

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        error = TaskError(
            stage="0olp",
            failure_type=FailureType.SUBMIT_FAILED,
            message="submit failed",
            timestamp=datetime.now(),
        )
        monitor.report_error(error)

        assert monitor.should_abort() is True

    def test_should_abort_node_error_exceeded(self):
        from deeplazy.monitor import JobMonitor
        from deeplazy.constants import DEFAULT_MAX_RETRIES

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        for i in range(4):
            error = TaskError(
                stage="0olp",
                failure_type=FailureType.NODE_ERROR,
                message=f"node error {i}",
                timestamp=datetime.now(),
            )
            monitor.report_error(error)

        assert monitor.should_abort() is True

    def test_should_not_abort_calc_error(self):
        from deeplazy.monitor import JobMonitor
        from deeplazy.constants import DEFAULT_MAX_RETRIES

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        for i in range(10):
            error = TaskError(
                stage="0olp",
                failure_type=FailureType.CALC_ERROR,
                message=f"calc error {i}",
                timestamp=datetime.now(),
            )
            monitor.report_error(error)

        assert monitor.should_abort() is False

    def test_trigger_abort(self):
        from deeplazy.monitor import JobMonitor
        from deeplazy.constants import DEFAULT_MAX_RETRIES

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        monitor.trigger_abort("manual abort")

        assert monitor.state.abort_flag is True
        assert monitor.state.abort_reason == "manual abort"
        assert monitor.should_abort() is True

    def test_save_and_restore_state(self):
        from deeplazy.monitor import JobMonitor
        from deeplazy.constants import DEFAULT_MAX_RETRIES

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        monitor.state.job_id = "12345"
        monitor.state.retry_counts[FailureType.NODE_ERROR] = 2

        state_data = monitor.save_state()

        new_monitor = JobMonitor(config)
        new_monitor.restore_from_state(state_data)

        assert new_monitor.state.job_id == "12345"
        assert new_monitor.state.retry_counts[FailureType.NODE_ERROR] == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_monitor.py::TestJobMonitor -v`
Expected: FAIL with "AttributeError: module 'deeplazy.monitor' has no attribute 'JobMonitor'"

- [ ] **Step 3: 实现 JobMonitor 类**

在 `deeplazy/monitor.py` 末尾添加:

```python
class JobMonitor:
    """统一作业监控管理器"""

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.state = MonitorState()
        self.logger = logging.getLogger(__name__)

    def report_error(self, error: TaskError) -> None:
        """报告任务执行错误"""
        self.state.errors.append(error)
        
        ftype = error.failure_type
        if ftype != FailureType.CALC_ERROR:
            self.state.retry_counts[ftype] = self.state.retry_counts.get(ftype, 0) + 1

        event = MonitorEvent(
            timestamp=datetime.now(),
            event_type=EventType.ERROR_REPORTED,
            stage=error.stage,
            job_id=self.state.job_id,
            message=f"{error.failure_type.value}: {error.message}",
        )
        self.log_event(event)

    def should_retry(self, failure_type: FailureType) -> bool:
        """判断是否应该重试"""
        max_retry = self.config.max_retries.get(failure_type, -1)
        
        if max_retry == 0:
            return False
        if max_retry < 0:
            return True
        
        current = self.state.retry_counts.get(failure_type, 0)
        return current < max_retry

    def get_retry_count(self, failure_type: FailureType) -> int:
        """获取当前重试次数"""
        return self.state.retry_counts.get(failure_type, 0)

    def should_abort(self) -> bool:
        """是否应该中断工作流"""
        if self.state.abort_flag:
            return True

        for ftype, max_retry in self.config.max_retries.items():
            current = self.state.retry_counts.get(ftype, 0)
            
            if max_retry == 0 and current > 0:
                return True
            if max_retry > 0 and current >= max_retry:
                return True

        return False

    def trigger_abort(self, reason: str) -> None:
        """触发快速失败"""
        self.state.abort_flag = True
        self.state.abort_reason = reason

        event = MonitorEvent(
            timestamp=datetime.now(),
            event_type=EventType.ABORT_TRIGGERED,
            stage="",
            job_id=self.state.job_id,
            message=reason,
        )
        self.log_event(event)

    def restore_from_state(self, state_data: Dict[str, Any]) -> None:
        """从状态数据恢复"""
        self.state = MonitorState.from_dict(state_data)

    def save_state(self) -> Dict[str, Any]:
        """保存状态数据"""
        return self.state.to_dict()

    def log_event(self, event: MonitorEvent) -> None:
        """记录监控事件"""
        level = logging.INFO
        if event.event_type in [EventType.JOB_FAILED, EventType.ABORT_TRIGGERED]:
            level = logging.ERROR
        elif event.event_type == EventType.RETRY_TRIGGERED:
            level = logging.WARNING

        self.logger.log(level, "[%s] %s", event.stage, event.message)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_monitor.py::TestJobMonitor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add deeplazy/monitor.py tests/test_monitor.py
git commit -m "feat: implement JobMonitor core methods"
```

---

## Chunk 3: 集成到现有模块

### Task 3.1: 修改 Context 添加 monitor 字段

**Files:**
- Modify: `deeplazy/contexts.py`

- [ ] **Step 1: 添加 monitor 字段到各 Context**

修改 `deeplazy/contexts.py`:

```python
# 在文件顶部添加导入
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .monitor import JobMonitor

# 修改 BaseContext
@dataclass
class BaseContext:
    """基础上下文"""
    config: Dict[str, Any]
    workflow_root: Path
    workdir: Path
    monitor: Optional[JobMonitor] = None

# 删除 OLPContext, InferContext, CalcContext 中的重复字段，继承自 BaseContext
```

完整修改后的文件:

```python
"""执行上下文定义 - 替代全局变量"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .monitor import JobMonitor


@dataclass
class BaseContext:
    """基础上下文"""
    config: Dict[str, Any]
    workflow_root: Path
    workdir: Path
    monitor: Optional[JobMonitor] = None


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
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from deeplazy.contexts import OLPContext, InferContext, CalcContext; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add deeplazy/contexts.py
git commit -m "feat: add monitor field to Context classes"
```

---

### Task 3.2: 修改 Executor 集成错误报告

**Files:**
- Modify: `deeplazy/executor.py`

- [ ] **Step 1: 添加错误报告逻辑**

在 `executor.py` 中:

1. 添加导入:
```python
from datetime import datetime
from .monitor import TaskError
from .exceptions import FailureType, AbortException
```

2. 修改 `run_olp_stage` 方法，添加 monitor 参数和错误报告:

```python
@staticmethod
def run_olp_stage(
    global_config: str,
    start: int,
    end: int,
    workdir: Optional[str] = None,
    stru_log: Optional[str] = None,
    monitor: Optional[JobMonitor] = None,
) -> Dict[str, int]:
    # ... 现有代码 ...
    
    # 4. 并行执行
    max_processes = ctx.max_processes
    with multiprocessing.Pool(processes=max_processes) as pool:
        execute_func = partial(OLPCommandExecutor.execute, ctx=ctx)
        results = pool.map(execute_func, records)

    # 5. 报告错误到 monitor
    if monitor:
        for i, (status, label) in enumerate(results):
            if status in ["failed", "node_error"]:
                ftype = FailureType.NODE_ERROR if status == "node_error" else FailureType.CALC_ERROR
                monitor.report_error(TaskError(
                    stage="0olp",
                    failure_type=ftype,
                    message=label,
                    timestamp=datetime.now(),
                ))
        
        if monitor.should_abort():
            raise AbortException(monitor.state.abort_reason)

    # 6. 统计结果
    stats = WorkflowExecutor._summarize_results(results)
    # ... 后续代码 ...
```

3. 同样修改 `run_calc_stage` 方法

- [ ] **Step 2: 验证导入**

Run: `python -c "from deeplazy.executor import WorkflowExecutor; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add deeplazy/executor.py
git commit -m "feat: integrate monitor error reporting in Executor"
```

---

### Task 3.3: 修改 WorkflowManager 集成 JobMonitor

**Files:**
- Modify: `deeplazy/workflow.py`

- [ ] **Step 1: 添加 JobMonitor 集成**

1. 添加导入:
```python
from .monitor import JobMonitor, MonitorConfig, SubmitResult
from .exceptions import FailureType, AbortException
from .constants import DEFAULT_MAX_RETRIES
```

2. 修改 `__init__` 方法:
```python
def __init__(self, config_path: Path, workdir: Path):
    # ... 现有代码 ...
    self.monitor = JobMonitor(MonitorConfig(max_retries=DEFAULT_MAX_RETRIES))
```

3. 修改 `_submit_job` 方法:
```python
def _submit_job(self, stage_name: str) -> Optional[str]:
    # ... 现有提交逻辑 ...
    
    if result.returncode != 0:
        self.monitor.report_error(TaskError(
            stage=stage_name,
            failure_type=FailureType.SUBMIT_FAILED,
            message=f"sbatch failed: {result.stderr}",
            timestamp=datetime.now(),
        ))
        return None
    
    # ... 后续代码 ...
```

4. 修改 `run` 方法中的状态检查:
```python
def run(self, daemon: bool = False):
    # ... 现有代码 ...
    
    while True:
        # 在每次循环开始检查 abort
        if self.monitor.should_abort():
            logger.error(f"快速失败: {self.monitor.state.abort_reason}")
            state["status"] = "aborted"
            state["abort_reason"] = self.monitor.state.abort_reason
            self._save_state(state)
            break
        
        # ... 现有代码 ...
        
        elif status == "failed":
            # 根据 job_state 判断失败类型
            job_state = details.get("job_state", "")
            if job_state in ["TIMEOUT", "NODE_FAIL"]:
                ftype = FailureType.NODE_ERROR
            else:
                ftype = FailureType.SLURM_FAILED
            
            self.monitor.report_error(TaskError(
                stage=current_stage,
                failure_type=ftype,
                message=details.get("reason", "job failed"),
                timestamp=datetime.now(),
            ))
            
            if self.monitor.should_abort():
                # ... 快速失败逻辑 ...
```

5. 在 `_save_state` 中保存 monitor 状态:
```python
def _save_state(self, state: Dict[str, Any]) -> None:
    state["monitor"] = self.monitor.save_state()
    # ... 现有代码 ...
```

6. 在 `_load_state` 中恢复 monitor 状态:
```python
def _load_state(self) -> Dict[str, Any]:
    # ... 现有代码 ...
    if "monitor" in state:
        self.monitor.restore_from_state(state["monitor"])
    return state
```

- [ ] **Step 2: 验证导入**

Run: `python -c "from deeplazy.workflow import WorkflowManager; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add deeplazy/workflow.py
git commit -m "feat: integrate JobMonitor in WorkflowManager"
```

---

## Chunk 4: 测试和验证

### Task 4.1: 运行完整测试

**Files:**
- All modified files

- [ ] **Step 1: 运行所有测试**

Run: `python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: 运行 CLI 测试**

Run: `python -m pytest tests/test_cli.py -v`
Expected: All PASS

- [ ] **Step 3: 验证导入完整性**

Run: `python -c "from deeplazy import WorkflowExecutor; from deeplazy.monitor import JobMonitor; from deeplazy.exceptions import FailureType, AbortException; print('All imports OK')"`
Expected: `All imports OK`

---

### Task 4.2: 最终提交

- [ ] **Step 1: 运行 lint 检查**

Run: `ruff check deeplazy/`
Expected: No errors (or fix if any)

- [ ] **Step 2: 确认所有更改已提交**

Run: `git status`
Expected: working tree clean

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: complete JobMonitor module implementation"
```

---

## 验收标准

1. `JobMonitor` 类实现所有核心方法
2. `FailureType` 枚举区分四种失败类型
3. `should_abort()` 根据失败类型和重试次数正确判断
4. `should_retry()` 正确判断是否应该重试
5. 状态可以持久化和恢复
6. 所有测试通过
7. 不影响现有功能
