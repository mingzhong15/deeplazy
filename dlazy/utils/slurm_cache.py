"""SLURM job state cache for reducing external command calls."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class JobState:
    """Cached job state information."""

    job_id: str
    state: str
    cached_at: float
    ttl: float = 60.0

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return time.time() - self.cached_at > self.ttl

    def is_terminal(self) -> bool:
        """Check if job is in terminal state."""
        return self.state in {
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "TIMEOUT",
            "NODE_FAIL",
            "OUT_OF_MEMORY",
        }


class SlurmStateCache:
    """Cache for SLURM job states to reduce external command calls."""

    def __init__(self, default_ttl: float = 60.0, terminal_ttl: float = 300.0):
        self._cache: Dict[str, JobState] = {}
        self.default_ttl = default_ttl
        self.terminal_ttl = terminal_ttl
        self._last_bulk_query: float = 0.0
        self._bulk_query_interval: float = 30.0

    def get_job_state(self, job_id: str) -> str:
        """Get job state with caching."""
        if not job_id:
            return "UNKNOWN"

        main_job_id = job_id.split("_")[0]
        cache_key = main_job_id

        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                return cached.state

        state = self._query_single_job(main_job_id)

        ttl = (
            self.terminal_ttl
            if state
            in {
                "COMPLETED",
                "FAILED",
                "CANCELLED",
                "TIMEOUT",
                "NODE_FAIL",
                "OUT_OF_MEMORY",
            }
            else self.default_ttl
        )

        self._cache[cache_key] = JobState(
            job_id=main_job_id,
            state=state,
            cached_at=time.time(),
            ttl=ttl,
        )

        return state

    def _query_single_job(self, job_id: str) -> str:
        """Query single job state via sacct."""
        result = subprocess.run(
            f"sacct -j {job_id} --format=State --noheader",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return "UNKNOWN"

        states = [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
        return states[0] if states else "UNKNOWN"

    def get_running_jobs(
        self, stage_name: str, user: Optional[str] = None
    ) -> List[str]:
        """Get running jobs for a stage with short-term caching."""
        if user is None:
            user = os.environ.get("USER", "")

        job_names = {
            "0olp": "B-olp",
            "1infer": "B-infer",
            "2calc": "B-calc",
        }

        job_name = job_names.get(stage_name)
        if not job_name:
            return []

        cache_key = f"running_{user}_{job_name}"

        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                return [] if cached.state == "NONE" else [cached.state]

        result = subprocess.run(
            f"squeue -u {user} -n '{job_name}' -h --format='%i'",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return []

        job_ids = [
            jid.strip() for jid in result.stdout.strip().split("\n") if jid.strip()
        ]

        if job_ids:
            self._cache[cache_key] = JobState(
                job_id=cache_key,
                state=job_ids[0],
                cached_at=time.time(),
                ttl=self.default_ttl,
            )
        else:
            self._cache[cache_key] = JobState(
                job_id=cache_key,
                state="NONE",
                cached_at=time.time(),
                ttl=self.default_ttl,
            )

        return job_ids

    def get_all_user_jobs(self, user: Optional[str] = None) -> Dict[str, str]:
        """Get all user jobs with short-term caching."""
        if user is None:
            user = os.environ.get("USER", "")

        cache_key = f"all_jobs_{user}"

        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                return {} if cached.state == "NONE" else eval(cached.state)

        result = subprocess.run(
            "squeue -u $USER -h --format='%i %j'",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return {}

        jobs = {}
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    jobs[parts[0]] = parts[1]

        self._cache[cache_key] = JobState(
            job_id=cache_key,
            state=repr(jobs),
            cached_at=time.time(),
            ttl=self.default_ttl,
        )

        return jobs

    def batch_check_states(self, job_ids: List[str]) -> Dict[str, str]:
        """Batch check multiple job states at once."""
        if not job_ids:
            return {}

        main_ids = [jid.split("_")[0] for jid in job_ids]
        unique_ids = list(set(main_ids))

        cached_results = {}
        uncached_ids = []

        for job_id in unique_ids:
            if job_id in self._cache:
                cached = self._cache[job_id]
                if not cached.is_expired():
                    cached_results[job_id] = cached.state
                else:
                    uncached_ids.append(job_id)
            else:
                uncached_ids.append(job_id)

        if uncached_ids:
            batch_results = self._batch_query_jobs(uncached_ids)
            for job_id, state in batch_results.items():
                ttl = (
                    self.terminal_ttl
                    if state
                    in {
                        "COMPLETED",
                        "FAILED",
                        "CANCELLED",
                        "TIMEOUT",
                        "NODE_FAIL",
                        "OUT_OF_MEMORY",
                    }
                    else self.default_ttl
                )

                self._cache[job_id] = JobState(
                    job_id=job_id,
                    state=state,
                    cached_at=time.time(),
                    ttl=ttl,
                )
            cached_results.update(batch_results)

        return cached_results

    def _batch_query_jobs(self, job_ids: List[str]) -> Dict[str, str]:
        """Query multiple jobs in a single sacct call."""
        if not job_ids:
            return {}

        job_list = ",".join(job_ids)
        result = subprocess.run(
            f"sacct -j {job_list} --format=JobID,State --noheader",
            shell=True,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return {jid: "UNKNOWN" for jid in job_ids}

        states = {}
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.strip().split()
                if len(parts) >= 2:
                    job_id = parts[0].split("_")[0]
                    state = parts[1]
                    if job_id not in states:
                        states[job_id] = state

        for jid in job_ids:
            if jid not in states:
                states[jid] = "UNKNOWN"

        return states

    def invalidate(self, job_id: Optional[str] = None) -> None:
        """Invalidate cache entries."""
        if job_id:
            main_id = job_id.split("_")[0]
            self._cache.pop(main_id, None)
        else:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove expired cache entries."""
        expired_keys = [key for key, state in self._cache.items() if state.is_expired()]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)


_global_cache: Optional[SlurmStateCache] = None


def get_slurm_cache() -> SlurmStateCache:
    """Get global SLURM state cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = SlurmStateCache()
    return _global_cache
