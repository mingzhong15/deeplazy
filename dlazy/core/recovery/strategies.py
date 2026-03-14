"""Recovery strategies for handling workflow errors."""

from __future__ import annotations

from typing import Any, Dict

from dlazy.core.exceptions import FailureType
from dlazy.core.recovery.base import RecoveryAction, RecoveryStrategy


class RetryStrategy(RecoveryStrategy):
    """Strategy for retrying failed tasks.

    Retries tasks that failed due to transient errors.
    """

    def __init__(self, max_retries: int = 3):
        """Initialize retry strategy.

        Args:
            max_retries: Maximum number of retry attempts
        """
        self.max_retries = max_retries

    def can_recover(self, context: Dict[str, Any]) -> bool:
        """Check if this strategy can handle the error.

        Args:
            context: Error context

        Returns:
            True if retry is possible
        """
        retry_count = context.get("retry_count", 0)
        failure_type = context.get("failure_type")

        # Can retry if under max retries and error is transient
        transient_errors = {
            FailureType.NODE_ERROR,
            FailureType.SLURM_FAILED,
            FailureType.SUBMIT_FAILED,
        }

        if isinstance(failure_type, str):
            failure_type = FailureType(failure_type)

        return retry_count < self.max_retries and failure_type in transient_errors

    def recover(self, context: Dict[str, Any]) -> RecoveryAction:
        """Return the recovery action.

        Args:
            context: Error context

        Returns:
            RETRY action
        """
        return RecoveryAction.RETRY


class SkipStrategy(RecoveryStrategy):
    """Strategy for skipping failed tasks.

    Skips tasks that cannot be recovered.
    """

    def __init__(self, permanent_failures: set = None):
        """Initialize skip strategy.

        Args:
            permanent_failures: Set of failure types that are permanent
        """
        self.permanent_failures = permanent_failures or {
            FailureType.CONFIG_ERROR,
            FailureType.SECURITY_ERROR,
        }

    def can_recover(self, context: Dict[str, Any]) -> bool:
        """Check if this strategy applies.

        Args:
            context: Error context

        Returns:
            True if error is permanent
        """
        failure_type = context.get("failure_type")

        if isinstance(failure_type, str):
            failure_type = FailureType(failure_type)

        return failure_type in self.permanent_failures

    def recover(self, context: Dict[str, Any]) -> RecoveryAction:
        """Return the recovery action.

        Args:
            context: Error context

        Returns:
            SKIP action
        """
        return RecoveryAction.SKIP


class AbortStrategy(RecoveryStrategy):
    """Strategy for aborting the workflow.

    Aborts when critical errors occur.
    """

    def __init__(self, critical_errors: set = None):
        """Initialize abort strategy.

        Args:
            critical_errors: Set of critical failure types
        """
        self.critical_errors = critical_errors or {
            FailureType.RESOURCE_ERROR,
        }

    def can_recover(self, context: Dict[str, Any]) -> bool:
        """Check if this strategy applies.

        Args:
            context: Error context

        Returns:
            True if error is critical
        """
        failure_type = context.get("failure_type")

        if isinstance(failure_type, str):
            failure_type = FailureType(failure_type)

        return failure_type in self.critical_errors

    def recover(self, context: Dict[str, Any]) -> RecoveryAction:
        """Return the recovery action.

        Args:
            context: Error context

        Returns:
            ABORT action
        """
        return RecoveryAction.ABORT


class RecoveryStrategyChain:
    """Chain of recovery strategies to try in order."""

    def __init__(self, strategies: list = None):
        """Initialize strategy chain.

        Args:
            strategies: List of RecoveryStrategy instances
        """
        self.strategies = strategies or [
            AbortStrategy(),
            SkipStrategy(),
            RetryStrategy(),
        ]

    def add_strategy(self, strategy: RecoveryStrategy) -> "RecoveryStrategyChain":
        """Add a strategy to the chain.

        Args:
            strategy: Strategy to add

        Returns:
            self for method chaining
        """
        self.strategies.append(strategy)
        return self

    def get_action(self, context: Dict[str, Any]) -> RecoveryAction:
        """Get the recovery action for an error.

        Args:
            context: Error context

        Returns:
            RecoveryAction to take
        """
        for strategy in self.strategies:
            if strategy.can_recover(context):
                return strategy.recover(context)

        # Default to skip if no strategy applies
        return RecoveryAction.SKIP

    def should_retry(self, context: Dict[str, Any]) -> bool:
        """Check if error should be retried.

        Args:
            context: Error context

        Returns:
            True if should retry
        """
        return self.get_action(context) == RecoveryAction.RETRY

    def should_skip(self, context: Dict[str, Any]) -> bool:
        """Check if error should be skipped.

        Args:
            context: Error context

        Returns:
            True if should skip
        """
        return self.get_action(context) == RecoveryAction.SKIP

    def should_abort(self, context: Dict[str, Any]) -> bool:
        """Check if workflow should abort.

        Args:
            context: Error context

        Returns:
            True if should abort
        """
        return self.get_action(context) == RecoveryAction.ABORT


# Default strategy chain
_default_chain = RecoveryStrategyChain()


def get_recovery_action(context: Dict[str, Any]) -> RecoveryAction:
    """Get recovery action for an error context.

    Args:
        context: Error context

    Returns:
        RecoveryAction to take
    """
    return _default_chain.get_action(context)


def map_failure_type_to_strategy(failure_type: FailureType) -> RecoveryAction:
    """Map failure type to default recovery action.

    Args:
        failure_type: Type of failure

    Returns:
        Default recovery action
    """
    context = {"failure_type": failure_type}
    return _default_chain.get_action(context)
