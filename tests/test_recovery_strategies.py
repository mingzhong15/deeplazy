"""Tests for recovery strategies."""

import pytest

from dlazy.core.exceptions import FailureType
from dlazy.core.recovery.base import RecoveryAction
from dlazy.core.recovery.strategies import (
    AbortStrategy,
    RecoveryStrategyChain,
    RetryStrategy,
    SkipStrategy,
    get_recovery_action,
    map_failure_type_to_strategy,
)


class TestRetryStrategy:
    """Tests for RetryStrategy."""

    def test_can_recover_transient_error(self):
        strategy = RetryStrategy(max_retries=3)

        context = {
            "failure_type": FailureType.NODE_ERROR,
            "retry_count": 0,
        }

        assert strategy.can_recover(context)

    def test_can_recover_with_retry_count(self):
        strategy = RetryStrategy(max_retries=3)

        context = {
            "failure_type": FailureType.NODE_ERROR,
            "retry_count": 2,
        }

        assert strategy.can_recover(context)

    def test_cannot_recover_exceeded_retries(self):
        strategy = RetryStrategy(max_retries=3)

        context = {
            "failure_type": FailureType.NODE_ERROR,
            "retry_count": 3,
        }

        assert not strategy.can_recover(context)

    def test_cannot_recover_permanent_error(self):
        strategy = RetryStrategy(max_retries=3)

        context = {
            "failure_type": FailureType.CONFIG_ERROR,
            "retry_count": 0,
        }

        assert not strategy.can_recover(context)

    def test_recover_returns_retry(self):
        strategy = RetryStrategy()
        context = {"failure_type": FailureType.NODE_ERROR}

        assert strategy.recover(context) == RecoveryAction.RETRY

    def test_can_recover_with_string_failure_type(self):
        strategy = RetryStrategy(max_retries=3)

        context = {
            "failure_type": "node_error",
            "retry_count": 0,
        }

        assert strategy.can_recover(context)


class TestSkipStrategy:
    """Tests for SkipStrategy."""

    def test_can_recover_config_error(self):
        strategy = SkipStrategy()

        context = {"failure_type": FailureType.CONFIG_ERROR}

        assert strategy.can_recover(context)

    def test_can_recover_security_error(self):
        strategy = SkipStrategy()

        context = {"failure_type": FailureType.SECURITY_ERROR}

        assert strategy.can_recover(context)

    def test_cannot_recover_transient_error(self):
        strategy = SkipStrategy()

        context = {"failure_type": FailureType.NODE_ERROR}

        assert not strategy.can_recover(context)

    def test_recover_returns_skip(self):
        strategy = SkipStrategy()
        context = {"failure_type": FailureType.CONFIG_ERROR}

        assert strategy.recover(context) == RecoveryAction.SKIP


class TestAbortStrategy:
    """Tests for AbortStrategy."""

    def test_can_recover_resource_error(self):
        strategy = AbortStrategy()

        context = {"failure_type": FailureType.RESOURCE_ERROR}

        assert strategy.can_recover(context)

    def test_recover_returns_abort(self):
        strategy = AbortStrategy()
        context = {"failure_type": FailureType.RESOURCE_ERROR}

        assert strategy.recover(context) == RecoveryAction.ABORT


class TestRecoveryStrategyChain:
    """Tests for RecoveryStrategyChain."""

    def test_get_action_retry(self):
        chain = RecoveryStrategyChain()

        context = {
            "failure_type": FailureType.NODE_ERROR,
            "retry_count": 0,
        }

        assert chain.get_action(context) == RecoveryAction.RETRY

    def test_get_action_skip(self):
        chain = RecoveryStrategyChain()

        context = {"failure_type": FailureType.CONFIG_ERROR}

        assert chain.get_action(context) == RecoveryAction.SKIP

    def test_get_action_abort(self):
        chain = RecoveryStrategyChain()

        context = {"failure_type": FailureType.RESOURCE_ERROR}

        assert chain.get_action(context) == RecoveryAction.ABORT

    def test_should_retry(self):
        chain = RecoveryStrategyChain()

        context = {
            "failure_type": FailureType.NODE_ERROR,
            "retry_count": 0,
        }

        assert chain.should_retry(context)

    def test_should_skip(self):
        chain = RecoveryStrategyChain()

        context = {"failure_type": FailureType.CONFIG_ERROR}

        assert chain.should_skip(context)

    def test_should_abort(self):
        chain = RecoveryStrategyChain()

        context = {"failure_type": FailureType.RESOURCE_ERROR}

        assert chain.should_abort(context)

    def test_add_strategy(self):
        chain = RecoveryStrategyChain()
        chain.add_strategy(SkipStrategy())

        assert len(chain.strategies) == 4


class TestGlobalFunctions:
    """Tests for global functions."""

    def test_get_recovery_action(self):
        context = {
            "failure_type": FailureType.NODE_ERROR,
            "retry_count": 0,
        }

        action = get_recovery_action(context)
        assert action == RecoveryAction.RETRY

    def test_map_failure_type_to_strategy(self):
        action = map_failure_type_to_strategy(FailureType.CONFIG_ERROR)
        assert action == RecoveryAction.SKIP

        action = map_failure_type_to_strategy(FailureType.RESOURCE_ERROR)
        assert action == RecoveryAction.ABORT
