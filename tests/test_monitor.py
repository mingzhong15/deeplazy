#!/usr/bin/env python3
"""测试 Monitor 模块"""

from datetime import datetime

import pytest

from deeplazy.exceptions import FailureType


class TestMonitorConfig:
    def test_default_config(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import MonitorConfig

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        assert config.max_retries[FailureType.SUBMIT_FAILED] == 0
        assert config.max_retries[FailureType.SLURM_FAILED] == 3


class TestMonitorState:
    def test_init(self):
        from deeplazy.monitor import MonitorState

        state = MonitorState()
        assert state.job_id is None
        assert state.abort_flag is False
        assert state.retry_counts == {}

    def test_to_dict(self):
        from deeplazy.monitor import MonitorState

        state = MonitorState(job_id="12345", abort_flag=True, abort_reason="test")
        data = state.to_dict()
        assert data["job_id"] == "12345"
        assert data["abort_flag"] is True

    def test_from_dict(self):
        from deeplazy.monitor import MonitorState

        data = {"job_id": "12345", "abort_flag": True, "abort_reason": "test"}
        state = MonitorState.from_dict(data)
        assert state.job_id == "12345"
        assert state.abort_flag is True


class TestTaskError:
    def test_init(self):
        from deeplazy.monitor import TaskError

        error = TaskError(
            stage="0olp",
            failure_type=FailureType.NODE_ERROR,
            message="test error",
            timestamp=datetime.now(),
        )
        assert error.stage == "0olp"
        assert error.failure_type == FailureType.NODE_ERROR


class TestJobMonitor:
    def test_init(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import JobMonitor, MonitorConfig

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)
        assert monitor.config.max_retries[FailureType.SUBMIT_FAILED] == 0

    def test_report_error(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import JobMonitor, MonitorConfig, TaskError

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        error = TaskError(
            stage="0olp",
            failure_type=FailureType.NODE_ERROR,
            message="test error",
            timestamp=datetime.now(),
        )
        monitor.report_error(error)

        assert FailureType.NODE_ERROR in monitor.state.retry_counts
        assert monitor.state.retry_counts[FailureType.NODE_ERROR] == 1

    def test_should_retry(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import JobMonitor, MonitorConfig

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        assert monitor.should_retry(FailureType.NODE_ERROR) is True
        assert monitor.should_retry(FailureType.SUBMIT_FAILED) is False
        assert monitor.should_retry(FailureType.CALC_ERROR) is True

    def test_should_abort_submit_failed(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import JobMonitor, MonitorConfig, TaskError

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        error = TaskError(
            stage="0olp",
            failure_type=FailureType.SUBMIT_FAILED,
            message="submit failed",
            timestamp=datetime.now(),
        )
        monitor.report_error(error)

        assert monitor.should_abort() is True

    def test_should_abort_node_error_exceeded(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import JobMonitor, MonitorConfig, TaskError

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        for i in range(4):
            error = TaskError(
                stage="0olp",
                failure_type=FailureType.NODE_ERROR,
                message=f"node error {i}",
                timestamp=datetime.now(),
            )
            monitor.report_error(error)

        assert monitor.should_abort() is True

    def test_should_not_abort_calc_error(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import JobMonitor, MonitorConfig, TaskError

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        for i in range(10):
            error = TaskError(
                stage="0olp",
                failure_type=FailureType.CALC_ERROR,
                message=f"calc error {i}",
                timestamp=datetime.now(),
            )
            monitor.report_error(error)

        assert monitor.should_abort() is False

    def test_trigger_abort(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import JobMonitor, MonitorConfig

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        monitor.trigger_abort("manual abort")

        assert monitor.state.abort_flag is True
        assert monitor.state.abort_reason == "manual abort"
        assert monitor.should_abort() is True

    def test_save_and_restore_state(self):
        from deeplazy.constants import DEFAULT_MAX_RETRIES
        from deeplazy.monitor import JobMonitor, MonitorConfig

        config = MonitorConfig(max_retries=DEFAULT_MAX_RETRIES)
        monitor = JobMonitor(config)

        monitor.state.job_id = "12345"
        monitor.state.retry_counts[FailureType.NODE_ERROR] = 2

        state_data = monitor.save_state()

        new_monitor = JobMonitor(config)
        new_monitor.restore_from_state(state_data)

        assert new_monitor.state.job_id == "12345"
        assert new_monitor.state.retry_counts[FailureType.NODE_ERROR] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
