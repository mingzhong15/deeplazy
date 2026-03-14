"""dlazy.core.recovery module."""

from dlazy.core.recovery.base import RecoveryAction, RecoveryContext, RecoveryStrategy
from dlazy.core.recovery.checksum import compute_checksum, verify_checksum
from dlazy.core.recovery.strategies import (
    AbortStrategy,
    RecoveryStrategyChain,
    RetryStrategy,
    SkipStrategy,
    get_recovery_action,
    map_failure_type_to_strategy,
)

__all__ = [
    "RecoveryAction",
    "RecoveryContext",
    "RecoveryStrategy",
    "compute_checksum",
    "verify_checksum",
    "RetryStrategy",
    "SkipStrategy",
    "AbortStrategy",
    "RecoveryStrategyChain",
    "get_recovery_action",
    "map_failure_type_to_strategy",
]
