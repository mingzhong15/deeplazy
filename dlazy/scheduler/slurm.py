"""SLURM scheduler implementation."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dlazy.scheduler.base import (
    JobInfo,
    JobStatus,
    Scheduler,
    SchedulerError,
    SubmitConfig,
)


class SlurmScheduler(Scheduler):
    """SLURM scheduler implementation.

    Uses direct sbatch/sacct/scancel commands for job management.
    """

    def __init__(self, retry_count: int = 3, retry_delay: float = 10.0):
        """Initialize SLURM scheduler.

        Args:
            retry_count: Number of retries for transient failures
            retry_delay: Seconds to wait between retries
        """
        self.retry_count = retry_count
        self.retry_delay = retry_delay

    def submit(self, script_path: Path, config: SubmitConfig) -> str:
        """Submit a job to SLURM.

        Args:
            script_path: Path to the job script
            config: Submission configuration

        Returns:
            Job ID string

        Raises:
            SchedulerError: If submission fails
        """
        script_path = Path(script_path)
        if not script_path.exists():
            raise SchedulerError(f"Script not found: {script_path}")

        args = config.to_sbatch_args()
        cmd = ["sbatch"] + args + [str(script_path)]

        for attempt in range(self.retry_count):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(script_path.parent),
                )

                if result.returncode == 0:
                    match = re.search(r"Submitted batch job (\d+)", result.stdout)
                    if match:
                        return match.group(1)
                    raise SchedulerError(
                        f"Could not parse job ID from output: {result.stdout}"
                    )

                error_msg = result.stderr.strip() or result.stdout.strip()

                if "Socket timed out" in error_msg or "Connection refused" in error_msg:
                    if attempt < self.retry_count - 1:
                        import time

                        time.sleep(self.retry_delay)
                        continue

                raise SchedulerError(f"sbatch failed: {error_msg}")

            except subprocess.TimeoutExpired:
                if attempt < self.retry_count - 1:
                    import time

                    time.sleep(self.retry_delay)
                    continue
                raise SchedulerError("sbatch command timed out")

            except Exception as e:
                if isinstance(e, SchedulerError):
                    raise
                raise SchedulerError(f"Unexpected error during submission: {e}")

        raise SchedulerError("Failed to submit job after all retries")

    def check_status(self, job_id: str) -> JobStatus:
        """Check the status of a SLURM job.

        Args:
            job_id: Job ID to check

        Returns:
            JobStatus enum value
        """
        try:
            result = subprocess.run(
                ["sacct", "-j", job_id, "-n", "-P", "-o", "State"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout.strip():
                states = result.stdout.strip().split("\n")
                for state in states:
                    state = state.strip()
                    if state:
                        return self._parse_state(state)

            result = subprocess.run(
                ["squeue", "-j", job_id, "-n", "-h", "-o", "%T"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout.strip():
                return self._parse_state(result.stdout.strip())

            return JobStatus.UNKNOWN

        except subprocess.TimeoutExpired:
            return JobStatus.UNKNOWN
        except Exception:
            return JobStatus.UNKNOWN

    def cancel(self, job_id: str) -> bool:
        """Cancel a SLURM job.

        Args:
            job_id: Job ID to cancel

        Returns:
            True if cancellation succeeded
        """
        try:
            result = subprocess.run(
                ["scancel", job_id],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_job_info(self, job_id: str) -> Optional[JobInfo]:
        """Get detailed information about a SLURM job.

        Args:
            job_id: Job ID to query

        Returns:
            JobInfo if found, None otherwise
        """
        try:
            result = subprocess.run(
                [
                    "sacct",
                    "-j",
                    job_id,
                    "-n",
                    "-P",
                    "-o",
                    "JobID,JobName,State,Submit,Start,End,ExitCode,NNode,NTasks,Partition,Timelimit",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0 or not result.stdout.strip():
                return None

            lines = result.stdout.strip().split("\n")
            if not lines:
                return None

            parts = lines[0].split("|")
            if len(parts) < 11:
                return None

            def parse_datetime(s: str) -> Optional[datetime]:
                if not s or s == "Unknown":
                    return None
                for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        return datetime.strptime(s, fmt)
                    except ValueError:
                        continue
                return None

            return JobInfo(
                job_id=job_id,
                status=self._parse_state(parts[2]),
                submit_time=parse_datetime(parts[3]) or datetime.now(),
                job_name=parts[1],
                nodes=int(parts[7]) if parts[7].isdigit() else 1,
                ppn=int(parts[8]) if parts[8].isdigit() else 1,
                partition=parts[9],
                time_limit=parts[10],
                start_time=parse_datetime(parts[4]),
                end_time=parse_datetime(parts[5]),
                exit_code=int(parts[6].split(":")[0]) if ":" in parts[6] else None,
            )

        except Exception:
            return None

    def _parse_state(self, state: str) -> JobStatus:
        """Parse SLURM state string to JobStatus.

        Args:
            state: SLURM state string

        Returns:
            JobStatus enum value
        """
        state = state.strip().upper()

        state_map = {
            "PENDING": JobStatus.PENDING,
            "PD": JobStatus.PENDING,
            "CONFIGURING": JobStatus.PENDING,
            "RUNNING": JobStatus.RUNNING,
            "R": JobStatus.RUNNING,
            "COMPLETED": JobStatus.COMPLETED,
            "CD": JobStatus.COMPLETED,
            "COMPLETING": JobStatus.RUNNING,
            "CG": JobStatus.RUNNING,
            "CANCELLED": JobStatus.CANCELLED,
            "CA": JobStatus.CANCELLED,
            "FAILED": JobStatus.FAILED,
            "F": JobStatus.FAILED,
            "NODE_FAIL": JobStatus.NODE_FAIL,
            "NF": JobStatus.NODE_FAIL,
            "TIMEOUT": JobStatus.TIMEOUT,
            "TO": JobStatus.TIMEOUT,
            "PREEMPTED": JobStatus.CANCELLED,
            "PR": JobStatus.CANCELLED,
            "BOOT_FAIL": JobStatus.FAILED,
            "BF": JobStatus.FAILED,
            "OUT_OF_MEMORY": JobStatus.FAILED,
            "OM": JobStatus.FAILED,
            "DEADLINE": JobStatus.TIMEOUT,
            "DL": JobStatus.TIMEOUT,
        }

        return state_map.get(state, JobStatus.UNKNOWN)

    def get_queue_status(self) -> Dict[str, int]:
        """Get queue status summary.

        Returns:
            Dict mapping state names to job counts
        """
        try:
            result = subprocess.run(
                ["squeue", "-u", "$USER", "-n", "-h", "-o", "%T"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            counts: Dict[str, int] = {}
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    state = line.strip()
                    if state:
                        counts[state] = counts.get(state, 0) + 1

            return counts

        except Exception:
            return {}

    def get_user_jobs(self) -> List[Dict]:
        """Get list of current user's jobs.

        Returns:
            List of job info dicts
        """
        try:
            result = subprocess.run(
                ["squeue", "-u", "$USER", "-o", "%i|%j|%T|%M|%D|%P"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            jobs = []
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    parts = line.strip().split("|")
                    if len(parts) >= 6 and parts[0].isdigit():
                        jobs.append(
                            {
                                "job_id": parts[0],
                                "name": parts[1],
                                "state": parts[2],
                                "time": parts[3],
                                "nodes": parts[4],
                                "partition": parts[5],
                            }
                        )

            return jobs

        except Exception:
            return []
