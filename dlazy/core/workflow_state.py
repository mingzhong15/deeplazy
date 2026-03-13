"""统一工作流监控 - 错误处理 + 重试决策 + 状态持久化"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from dlazy.core.exceptions import FailureType

if TYPE_CHECKING:
    from dlazy.path_resolver import BatchPathResolver


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
class ErrorRecord:
    """统一错误记录 - 合并 TaskError + ErrorTask"""

    path: str
    stage: str
    failure_type: FailureType = FailureType.CALC_ERROR
    message: str = ""
    batch_id: str = ""
    task_id: str = ""
    retry_count: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    error: str = ""  # 兼容旧参数

    def __post_init__(self):
        if self.message == "" and self.error:
            self.message = self.error
        if self.failure_type is None:
            self.failure_type = FailureType.CALC_ERROR

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "path": self.path,
            "stage": self.stage,
            "failure_type": self.failure_type.value,
            "message": self.message or self.error,
            "batch_id": self.batch_id,
            "task_id": self.task_id,
            "retry_count": self.retry_count,
            "timestamp": self.timestamp.isoformat(),
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorRecord":
        return cls(
            path=data["path"],
            stage=data["stage"],
            failure_type=FailureType(data["failure_type"]),
            message=data["message"],
            batch_id=data["batch_id"],
            task_id=data["task_id"],
            retry_count=data.get("retry_count", 0),
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass
class MonitorState:
    """监控状态"""

    job_id: Optional[str] = None
    retry_counts: Dict[FailureType, int] = field(default_factory=dict)
    abort_flag: bool = False
    abort_reason: Optional[str] = None
    errors: List[ErrorRecord] = field(default_factory=list)

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

        errors = [ErrorRecord.from_dict(e) for e in data.get("errors", [])]

        return cls(
            job_id=data.get("job_id"),
            retry_counts=retry_counts,
            abort_flag=data.get("abort_flag", False),
            abort_reason=data.get("abort_reason"),
            errors=errors,
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
class MonitorConfig:
    """监控配置"""

    max_retries: Dict[FailureType, int] = field(
        default_factory=lambda: {
            FailureType.NODE_ERROR: 3,
            FailureType.SLURM_FAILED: 2,
            FailureType.SUBMIT_FAILED: 2,
            FailureType.CALC_ERROR: 1,
        }
    )


class WorkflowMonitor:
    """统一工作流监控管理器 - 合并 JobMonitor + error_handler 功能"""

    def __init__(
        self,
        config: Optional[MonitorConfig] = None,
        resolver: Optional["BatchPathResolver"] = None,
    ):
        self.config = config or MonitorConfig()
        self.resolver = resolver
        self.state = MonitorState()
        self.logger = logging.getLogger("dlazy.monitor")

    def record_error(
        self,
        path: str,
        stage: str,
        failure_type: FailureType,
        message: str,
        batch_id: str,
        task_id: str,
    ) -> ErrorRecord:
        """统一错误记录 - 内存 + 文件"""
        retry_count = self.state.retry_counts.get(failure_type, 0)
        record = ErrorRecord(
            path=path,
            stage=stage,
            failure_type=failure_type,
            message=message,
            batch_id=batch_id,
            task_id=task_id,
            retry_count=retry_count,
        )

        self.state.errors.append(record)
        if failure_type != FailureType.CALC_ERROR:
            self.state.retry_counts[failure_type] = retry_count + 1

        if self.resolver:
            self._write_error_to_file(record)

        event = MonitorEvent(
            timestamp=datetime.now(),
            event_type=EventType.ERROR_REPORTED,
            stage=stage,
            job_id=self.state.job_id,
            message=f"{failure_type.value}: {message}",
        )
        self._log_event(event)

        return record

    def _write_error_to_file(self, record: ErrorRecord) -> None:
        """写入错误到文件"""
        if not self.resolver:
            return

        from dlazy.utils.concurrency import atomic_append_jsonl

        if record.stage == "olp":
            error_file = self.resolver.get_olp_error_file()
        elif record.stage == "infer":
            error_file = self.resolver.get_infer_error_file()
        elif record.stage == "calc":
            error_file = self.resolver.get_calc_error_file()
        else:
            raise ValueError(f"Unknown stage: {record.stage}")

        atomic_append_jsonl(error_file, [record.to_dict()])

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
        self._log_event(event)

    def restore_from_state(self, state_data: Dict[str, Any]) -> None:
        """从状态数据恢复"""
        self.state = MonitorState.from_dict(state_data)

    def save_state(self) -> Dict[str, Any]:
        """保存状态数据"""
        return self.state.to_dict()

    def _log_event(self, event: MonitorEvent) -> None:
        """记录监控事件"""
        level = logging.INFO
        if event.event_type in [EventType.JOB_FAILED, EventType.ABORT_TRIGGERED]:
            level = logging.ERROR
        elif event.event_type == EventType.RETRY_TRIGGERED:
            level = logging.WARNING

        self.logger.log(level, "[%s] %s", event.stage, event.message)

    def get_errors(self, stage: Optional[str] = None) -> List[ErrorRecord]:
        """获取错误记录"""
        if stage is None:
            return self.state.errors.copy()
        return [e for e in self.state.errors if e.stage == stage]

    def get_error_count(self, stage: Optional[str] = None) -> int:
        """获取错误数量"""
        return len(self.get_errors(stage))


# 兼容性别名
JobMonitor = WorkflowMonitor
TaskError = ErrorRecord
ErrorTask = ErrorRecord  # 兼容旧名称


# 兼容旧 API 的错误上下文
@dataclass
class ErrorContext:
    """Error context for recording failed tasks."""

    path: str
    stage: str
    error: str
    batch_index: int
    task_id: str
    resolver: "BatchPathResolver"


def record_error(ctx: ErrorContext, monitor: Optional[WorkflowMonitor] = None) -> None:
    """Record an error task - 兼容旧 API"""
    if monitor is None:
        from dlazy.utils.concurrency import atomic_append_jsonl

        error_task = {
            "path": ctx.path,
            "stage": ctx.stage,
            "error": ctx.error,
            "batch_id": str(ctx.batch_index),
            "task_id": ctx.task_id,
            "retry_count": 0,
        }

        if ctx.stage == "olp":
            error_file = ctx.resolver.get_olp_error_file()
        elif ctx.stage == "infer":
            error_file = ctx.resolver.get_infer_error_file()
        elif ctx.stage == "calc":
            error_file = ctx.resolver.get_calc_error_file()
        else:
            raise ValueError(f"Unknown stage: {ctx.stage}")

        atomic_append_jsonl(error_file, [error_task])
    else:
        monitor.record_error(
            path=ctx.path,
            stage=ctx.stage,
            failure_type=FailureType.CALC_ERROR,
            message=ctx.error,
            batch_id=str(ctx.batch_index),
            task_id=ctx.task_id,
        )


# 任务重试计数查询
def get_task_retry_count(workflow_root: Path, task_path: str) -> int:
    """Count how many times a task has failed across all batches."""
    count = 0
    batch_dirs = sorted(workflow_root.glob("batch.*"))
    for batch_dir in batch_dirs:
        error_files = list(batch_dir.rglob("error_tasks.jsonl"))
        for ef in error_files:
            if ef.exists():
                with open(ef, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                d = json.loads(line)
                                if d.get("path") == task_path:
                                    count += 1
                            except json.JSONDecodeError:
                                pass
    return count


# 兼容旧 API
def append_error_task(filepath: Path, task: Union[ErrorRecord, Dict[str, Any]]) -> None:
    """Append an error task - 兼容旧 API"""
    from dlazy.utils.concurrency import atomic_append_jsonl

    if isinstance(task, ErrorRecord):
        record = task.to_dict()
    else:
        record = task
    atomic_append_jsonl(filepath, [record])
