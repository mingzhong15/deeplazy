"""Validator registry for managing validators."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Type

from dlazy.core.validator.base import Validator


# Global registry
_validators: Dict[str, Type[Validator]] = {}


def register_validator(name: str) -> Callable[[Type[Validator]], Type[Validator]]:
    """Decorator to register a validator.

    Args:
        name: Name to register the validator under

    Returns:
        Decorator function

    Example:
        @register_validator("scf_convergence")
        class SCFConvergenceValidator(Validator):
            ...
    """

    def decorator(cls: Type[Validator]) -> Type[Validator]:
        cls.validator_type = name
        _validators[name] = cls
        return cls

    return decorator


def get_validator(name: str) -> Optional[Type[Validator]]:
    """Get a registered validator by name.

    Args:
        name: Name of the validator

    Returns:
        Validator class or None if not found
    """
    return _validators.get(name)


def get_all_validators() -> List[Type[Validator]]:
    """Get all registered validators.

    Returns:
        List of validator classes
    """
    return list(_validators.values())


def get_validator_names() -> List[str]:
    """Get names of all registered validators.

    Returns:
        List of validator names
    """
    return list(_validators.keys())


def clear_registry() -> None:
    """Clear all registered validators. Mainly for testing."""
    _validators.clear()


class ValidatorRegistry:
    """Registry for managing validators.

    This class provides an object-oriented interface to the validator registry.
    """

    def __init__(self):
        """Initialize the registry."""
        self._validators: Dict[str, Type[Validator]] = {}

    def register(self, name: str, validator_cls: Type[Validator]) -> None:
        """Register a validator.

        Args:
            name: Name to register under
            validator_cls: Validator class to register
        """
        validator_cls.validator_type = name
        self._validators[name] = validator_cls

    def get(self, name: str) -> Optional[Type[Validator]]:
        """Get a validator by name.

        Args:
            name: Name of the validator

        Returns:
            Validator class or None
        """
        return self._validators.get(name)

    def get_all(self) -> List[Type[Validator]]:
        """Get all registered validators.

        Returns:
            List of validator classes
        """
        return list(self._validators.values())

    def get_names(self) -> List[str]:
        """Get names of all registered validators.

        Returns:
            List of validator names
        """
        return list(self._validators.keys())

    def create(self, name: str, **kwargs) -> Optional[Validator]:
        """Create a validator instance by name.

        Args:
            name: Name of the validator
            **kwargs: Arguments to pass to validator constructor

        Returns:
            Validator instance or None if not found
        """
        validator_cls = self._validators.get(name)
        if validator_cls is None:
            return None
        return validator_cls(**kwargs)

    def get_validators_for_stage(self, stage: str) -> List[Type[Validator]]:
        """Get validators applicable to a stage.

        Args:
            stage: Stage name (olp, infer, calc)

        Returns:
            List of applicable validator classes
        """
        # Default mapping of validators to stages
        stage_validators = {
            "olp": ["hdf5_integrity"],  # OLP outputs HDF5
            "infer": ["hdf5_integrity"],  # Infer outputs HDF5
            "calc": ["scf_convergence", "hdf5_integrity"],  # Calc needs SCF + HDF5
        }

        names = stage_validators.get(stage, [])
        return [self._validators[n] for n in names if n in self._validators]

    def __contains__(self, name: str) -> bool:
        return name in self._validators

    def __len__(self) -> int:
        return len(self._validators)
