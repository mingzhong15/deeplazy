"""Tests for SLURM scheduler."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from dlazy.scheduler.base import JobInfo, JobStatus, SubmitConfig
from dlazy.scheduler.slurm import SlurmScheduler


class TestSlurmScheduler:
    """Tests for SlurmScheduler."""

    def test_submit_success(self, tmp_path):
        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Submitted batch job 12345", stderr=""
            )

            scheduler = SlurmScheduler()
            config = SubmitConfig(job_name="test_job", nodes=1, ppn=24)
            job_id = scheduler.submit(script, config)

            assert job_id == "12345"
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "sbatch" in cmd

    def test_submit_script_not_found(self):
        scheduler = SlurmScheduler()
        config = SubmitConfig(job_name="test")

        with pytest.raises(Exception) as exc_info:
            scheduler.submit(Path("/nonexistent/script.sh"), config)

        assert "not found" in str(exc_info.value).lower()

    def test_submit_failure(self, tmp_path):
        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="sbatch: error: Invalid partition"
            )

            scheduler = SlurmScheduler()
            config = SubmitConfig(job_name="test")

            with pytest.raises(Exception) as exc_info:
                scheduler.submit(script, config)

            assert "failed" in str(exc_info.value).lower()

    def test_check_status_completed(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="COMPLETED", stderr=""
            )

            scheduler = SlurmScheduler()
            status = scheduler.check_status("12345")

            assert status == JobStatus.COMPLETED

    def test_check_status_running(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="RUNNING", stderr="")

            scheduler = SlurmScheduler()
            status = scheduler.check_status("12345")

            assert status == JobStatus.RUNNING

    def test_check_status_pending(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="PENDING", stderr="")

            scheduler = SlurmScheduler()
            status = scheduler.check_status("12345")

            assert status == JobStatus.PENDING

    def test_check_status_failed(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="FAILED", stderr="")

            scheduler = SlurmScheduler()
            status = scheduler.check_status("12345")

            assert status == JobStatus.FAILED

    def test_check_status_timeout(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="TIMEOUT", stderr="")

            scheduler = SlurmScheduler()
            status = scheduler.check_status("12345")

            assert status == JobStatus.TIMEOUT

    def test_cancel_success(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            scheduler = SlurmScheduler()
            result = scheduler.cancel("12345")

            assert result is True
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "scancel" in cmd
            assert "12345" in cmd

    def test_cancel_failure(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            scheduler = SlurmScheduler()
            result = scheduler.cancel("12345")

            assert result is False

    def test_get_job_info(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="12345|test_job|COMPLETED|2024-01-01T10:00:00|2024-01-01T10:30:00|2024-01-01T11:00:00|0:0|1|24|normal|1:00:00",
                stderr="",
            )

            scheduler = SlurmScheduler()
            info = scheduler.get_job_info("12345")

            assert info is not None
            assert info.job_id == "12345"
            assert info.job_name == "test_job"
            assert info.status == JobStatus.COMPLETED

    def test_get_job_info_not_found(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")

            scheduler = SlurmScheduler()
            info = scheduler.get_job_info("nonexistent")

            assert info is None

    def test_parse_state_abbreviations(self):
        scheduler = SlurmScheduler()

        assert scheduler._parse_state("R") == JobStatus.RUNNING
        assert scheduler._parse_state("PD") == JobStatus.PENDING
        assert scheduler._parse_state("CG") == JobStatus.RUNNING
        assert scheduler._parse_state("CD") == JobStatus.COMPLETED
        assert scheduler._parse_state("F") == JobStatus.FAILED
        assert scheduler._parse_state("TO") == JobStatus.TIMEOUT
        assert scheduler._parse_state("NF") == JobStatus.NODE_FAIL
        assert scheduler._parse_state("CA") == JobStatus.CANCELLED

    def test_parse_state_full_names(self):
        scheduler = SlurmScheduler()

        assert scheduler._parse_state("RUNNING") == JobStatus.RUNNING
        assert scheduler._parse_state("PENDING") == JobStatus.PENDING
        assert scheduler._parse_state("COMPLETED") == JobStatus.COMPLETED
        assert scheduler._parse_state("FAILED") == JobStatus.FAILED
        assert scheduler._parse_state("TIMEOUT") == JobStatus.TIMEOUT
        assert scheduler._parse_state("NODE_FAIL") == JobStatus.NODE_FAIL
        assert scheduler._parse_state("CANCELLED") == JobStatus.CANCELLED

    def test_parse_state_unknown(self):
        scheduler = SlurmScheduler()

        assert scheduler._parse_state("UNKNOWN_STATE") == JobStatus.UNKNOWN
        assert scheduler._parse_state("") == JobStatus.UNKNOWN

    def test_get_queue_status(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="RUNNING\nRUNNING\nPENDING\n",
                stderr="",
            )

            scheduler = SlurmScheduler()
            status = scheduler.get_queue_status()

            assert status.get("RUNNING") == 2
            assert status.get("PENDING") == 1

    def test_get_user_jobs(self):
        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="12345|job1|RUNNING|1:00:00|2|normal\n67890|job2|PENDING|0:00:00|1|gpu\n",
                stderr="",
            )

            scheduler = SlurmScheduler()
            jobs = scheduler.get_user_jobs()

            assert len(jobs) == 2
            assert jobs[0]["job_id"] == "12345"
            assert jobs[0]["name"] == "job1"
            assert jobs[1]["job_id"] == "67890"

    def test_submit_with_retry(self, tmp_path):
        script = tmp_path / "submit.sh"
        script.write_text("#!/bin/bash\necho test")

        with patch("dlazy.scheduler.slurm.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="Socket timed out"),
                MagicMock(returncode=1, stdout="", stderr="Connection refused"),
                MagicMock(returncode=0, stdout="Submitted batch job 99999", stderr=""),
            ]

            scheduler = SlurmScheduler(retry_count=3, retry_delay=0.01)
            config = SubmitConfig(job_name="test")

            job_id = scheduler.submit(script, config)
            assert job_id == "99999"
            assert mock_run.call_count == 3
