"""作业监控模块 - 统一管理作业状态监控、错误处理、重试决策"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from .exceptions import FailureType

if TYPE_CHECKING:
    pass


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
    state: str
    exit_code: Optional[int] = None


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
