"""Scheduler base classes and interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class JobStatus(Enum):
    """Status of a SLURM job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    NODE_FAIL = "NODE_FAIL"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value

    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMEOUT,
            JobStatus.NODE_FAIL,
        )

    def is_success(self) -> bool:
        """Check if this is a successful terminal state."""
        return self == JobStatus.COMPLETED


@dataclass
class JobInfo:
    """Information about a submitted job."""

    job_id: str
    status: JobStatus
    submit_time: datetime
    job_name: str = ""
    nodes: int = 1
    ppn: int = 1
    partition: str = ""
    time_limit: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    exit_code: Optional[int] = None

    def duration_seconds(self) -> Optional[int]:
        """Calculate job duration in seconds."""
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds())
        return None


@dataclass
class SubmitConfig:
    """Configuration for job submission."""

    job_name: str
    nodes: int = 0
    ppn: int = 0
    time_limit: str = ""
    partition: str = ""
    qos: str = ""
    memory: str = ""
    output_file: str = "slurm-%j.out"
    error_file: str = "slurm-%j.err"
    extra_args: Dict[str, str] = field(default_factory=dict)

    def to_sbatch_args(self) -> List[str]:
        """Convert to sbatch command line arguments."""
        args = [
            f"--job-name={self.job_name}",
            f"--output={self.output_file}",
            f"--error={self.error_file}",
        ]
        if self.nodes > 0:
            args.append(f"--nodes={self.nodes}")
        if self.ppn > 0:
            args.append(f"--ntasks-per-node={self.ppn}")
        if self.time_limit:
            args.append(f"--time={self.time_limit}")
        if self.partition:
            args.append(f"--partition={self.partition}")
        if self.qos:
            args.append(f"--qos={self.qos}")
        if self.memory:
            args.append(f"--mem={self.memory}")
        for key, value in self.extra_args.items():
            args.append(f"--{key}={value}")
        return args


class SchedulerError(Exception):
    """Exception raised for scheduler-related errors."""

    def __init__(self, message: str, job_id: Optional[str] = None):
        super().__init__(message)
        self.job_id = job_id


class Scheduler(ABC):
    """Abstract base class for job schedulers.

    This is designed for SLURM only, following the "SLURM only" guardrail.
    """

    @abstractmethod
    def submit(self, script_path: Path, config: SubmitConfig) -> str:
        """Submit a job to the scheduler.

        Args:
            script_path: Path to the job script
            config: Submission configuration

        Returns:
            Job ID string

        Raises:
            SchedulerError: If submission fails
        """
        pass

    @abstractmethod
    def check_status(self, job_id: str) -> JobStatus:
        """Check the status of a submitted job.

        Args:
            job_id: Job ID to check

        Returns:
            JobStatus enum value
        """
        pass

    @abstractmethod
    def cancel(self, job_id: str) -> bool:
        """Cancel a submitted job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancellation succeeded
        """
        pass

    @abstractmethod
    def get_job_info(self, job_id: str) -> Optional[JobInfo]:
        """Get detailed information about a job.

        Args:
            job_id: Job ID to query

        Returns:
            JobInfo if found, None otherwise
        """
        pass

    def wait_for_completion(
        self,
        job_id: str,
        timeout_seconds: int = 86400,
        poll_interval: int = 60,
    ) -> JobStatus:
        """Wait for a job to complete.

        Args:
            job_id: Job ID to wait for
            timeout_seconds: Maximum time to wait
            poll_interval: Seconds between status checks

        Returns:
            Final JobStatus
        """
        import time

        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            status = self.check_status(job_id)
            if status.is_terminal():
                return status
            time.sleep(poll_interval)

        return JobStatus.UNKNOWN
