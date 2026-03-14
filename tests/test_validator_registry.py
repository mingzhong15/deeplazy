"""Tests for validator registry."""

import pytest

from dlazy.core.validator.base import Validator, ValidationResult
from dlazy.core.validator.registry import (
    ValidatorRegistry,
    clear_registry,
    get_all_validators,
    get_validator,
    get_validator_names,
    register_validator,
)


class MockValidator(Validator):
    """Mock validator for testing."""

    validator_type = "mock"

    def validate(self, path):
        return ValidationResult(is_valid=True)


class TestValidatorRegistry:
    """Tests for ValidatorRegistry."""

    def setup_method(self):
        clear_registry()

    def test_register_decorator(self, tmp_path):
        @register_validator("test_validator")
        class TestValidator(Validator):
            validator_type = "test_validator"

            def validate(self, path):
                return ValidationResult(is_valid=True)

        assert get_validator("test_validator") is TestValidator

    def test_get_validator_not_found(self):
        result = get_validator("nonexistent")
        assert result is None

    def test_get_all_validators(self):
        @register_validator("v1")
        class V1(Validator):
            validator_type = "v1"

            def validate(self, path):
                return ValidationResult(is_valid=True)

        @register_validator("v2")
        class V2(Validator):
            validator_type = "v2"

            def validate(self, path):
                return ValidationResult(is_valid=True)

        all_validators = get_all_validators()
        assert len(all_validators) >= 2

    def test_get_validator_names(self):
        clear_registry()

        @register_validator("alpha")
        class Alpha(Validator):
            validator_type = "alpha"

            def validate(self, path):
                return ValidationResult(is_valid=True)

        names = get_validator_names()
        assert "alpha" in names

    def test_registry_instance(self):
        registry = ValidatorRegistry()

        registry.register("mock", MockValidator)

        assert registry.get("mock") is MockValidator
        assert "mock" in registry
        assert len(registry) == 1

    def test_registry_create(self, tmp_path):
        registry = ValidatorRegistry()
        registry.register("mock", MockValidator)

        validator = registry.create("mock")
        assert isinstance(validator, MockValidator)

    def test_registry_create_not_found(self):
        registry = ValidatorRegistry()
        result = registry.create("nonexistent")
        assert result is None

    def test_registry_get_validators_for_stage(self):
        registry = ValidatorRegistry()
        registry.register("scf_convergence", MockValidator)
        registry.register("hdf5_integrity", MockValidator)

        validators = registry.get_validators_for_stage("calc")
        assert len(validators) == 2
        assert all(v is MockValidator for v in validators)

    def test_registry_get_validators_for_olp_stage(self):
        registry = ValidatorRegistry()
        registry.register("hdf5_integrity", MockValidator)

        validators = registry.get_validators_for_stage("olp")
        assert len(validators) == 1


class TestGlobalFunctions:
    """Tests for global registry functions."""

    def setup_method(self):
        clear_registry()

    def test_clear_registry(self):
        @register_validator("temp")
        class Temp(Validator):
            validator_type = "temp"

            def validate(self, path):
                return ValidationResult(is_valid=True)

        assert get_validator("temp") is not None
        clear_registry()
        assert get_validator("temp") is None
