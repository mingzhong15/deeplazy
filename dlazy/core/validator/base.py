"""Validator base classes and interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ValidationResult:
    """Result of a validation operation.

    Attributes:
        is_valid: Whether the validation passed
        errors: List of error messages
        warnings: List of warning messages
        details: Additional details about the validation
    """

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """Allow using ValidationResult in boolean context."""
        return self.is_valid

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another ValidationResult into this one."""
        return ValidationResult(
            is_valid=self.is_valid and other.is_valid,
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
            details={**self.details, **other.details},
        )


class Validator(ABC):
    """Abstract base class for validators.

    Validators check files or directories for specific conditions.
    """

    validator_type: str = "base"

    @abstractmethod
    def validate(self, path: Path) -> ValidationResult:
        """Validate a file or directory.

        Args:
            path: Path to the file or directory to validate

        Returns:
            ValidationResult with is_valid, errors, warnings, and details
        """
        pass

    def __call__(self, path: Path) -> ValidationResult:
        """Allow using validator as a callable."""
        return self.validate(path)
