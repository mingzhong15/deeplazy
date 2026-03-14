"""Recovery strategy base classes and interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict


class RecoveryAction(Enum):
    """Actions that can be taken when an error occurs."""

    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"

    def __str__(self) -> str:
        return self.value


class RecoveryStrategy(ABC):
    """Abstract base class for recovery strategies.

    Recovery strategies determine how to handle errors during workflow execution.
    """

    @abstractmethod
    def can_recover(self, context: Dict[str, Any]) -> bool:
        """Check if this strategy can handle the error.

        Args:
            context: Dictionary containing error context including:
                - failure_type: Type of failure
                - retry_count: Number of retry attempts
                - error_message: Error message
                - task_id: Task identifier

        Returns:
            True if this strategy can handle the error
        """
        pass

    @abstractmethod
    def recover(self, context: Dict[str, Any]) -> RecoveryAction:
        """Return the recovery action to take.

        Args:
            context: Dictionary containing error context

        Returns:
            RecoveryAction indicating what to do next
        """
        pass


class RecoveryContext:
    """Builder for recovery context dictionaries."""

    def __init__(self):
        self._context: Dict[str, Any] = {}

    def with_failure_type(self, failure_type: str) -> RecoveryContext:
        """Add failure type to context."""
        self._context["failure_type"] = failure_type
        return self

    def with_retry_count(self, count: int) -> RecoveryContext:
        """Add retry count to context."""
        self._context["retry_count"] = count
        return self

    def with_error_message(self, message: str) -> RecoveryContext:
        """Add error message to context."""
        self._context["error_message"] = message
        return self

    def with_task_id(self, task_id: str) -> RecoveryContext:
        """Add task ID to context."""
        self._context["task_id"] = task_id
        return self

    def with_stage(self, stage: str) -> RecoveryContext:
        """Add stage to context."""
        self._context["stage"] = stage
        return self

    def build(self) -> Dict[str, Any]:
        """Build and return the context dictionary."""
        return self._context.copy()
