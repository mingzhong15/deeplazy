"""dlazy.core.validator module."""

from dlazy.core.validator.base import Validator, ValidationResult
from dlazy.core.validator.registry import (
    ValidatorRegistry,
    register_validator,
    get_validator,
    get_all_validators,
)

__all__ = [
    "Validator",
    "ValidationResult",
    "ValidatorRegistry",
    "register_validator",
    "get_validator",
    "get_all_validators",
]
