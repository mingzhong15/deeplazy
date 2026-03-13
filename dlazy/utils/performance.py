"""Performance monitoring and profiling utilities."""

from __future__ import annotations

import functools
import time
import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional


_perf_logger = logging.getLogger("deeplazy.performance")
_perf_stats: Dict[str, Dict[str, Any]] = {}


class PerformanceMonitor:
    """Performance monitoring context manager and decorator."""

    def __init__(self, name: str, threshold_ms: float = 100.0):
        self.name = name
        self.threshold_ms = threshold_ms
        self.start_time: Optional[float] = None
        self.elapsed_ms: float = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000

        if self.elapsed_ms > self.threshold_ms:
            _perf_logger.warning(
                "[PERF] %s took %.2f ms (threshold: %.2f ms)",
                self.name,
                self.elapsed_ms,
                self.threshold_ms,
            )
        else:
            _perf_logger.debug(
                "[PERF] %s took %.2f ms",
                self.name,
                self.elapsed_ms,
            )

        if self.name not in _perf_stats:
            _perf_stats[self.name] = {
                "count": 0,
                "total_ms": 0.0,
                "max_ms": 0.0,
                "min_ms": float("inf"),
            }

        stats = _perf_stats[self.name]
        stats["count"] += 1
        stats["total_ms"] += self.elapsed_ms
        stats["max_ms"] = max(stats["max_ms"], self.elapsed_ms)
        stats["min_ms"] = min(stats["min_ms"], self.elapsed_ms)

    @staticmethod
    def track(name: Optional[str] = None, threshold_ms: float = 100.0):
        """Decorator to track function performance."""

        def decorator(func: Callable) -> Callable:
            track_name = name or f"{func.__module__}.{func.__name__}"

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with PerformanceMonitor(track_name, threshold_ms):
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    @staticmethod
    def get_stats() -> Dict[str, Dict[str, Any]]:
        """Get performance statistics."""
        return _perf_stats.copy()

    @staticmethod
    def reset_stats() -> None:
        """Reset performance statistics."""
        _perf_stats.clear()

    @staticmethod
    def print_summary() -> None:
        """Print performance summary."""
        if not _perf_stats:
            print("No performance data collected")
            return

        print("\n=== Performance Summary ===")
        print(
            f"{'Operation':<40} {'Count':>8} {'Avg(ms)':>10} {'Min(ms)':>10} {'Max(ms)':>10}"
        )
        print("-" * 80)

        for name, stats in sorted(
            _perf_stats.items(), key=lambda x: x[1]["total_ms"], reverse=True
        ):
            avg_ms = stats["total_ms"] / stats["count"] if stats["count"] > 0 else 0
            print(
                f"{name:<40} {stats['count']:>8} {avg_ms:>10.2f} "
                f"{stats['min_ms']:>10.2f} {stats['max_ms']:>10.2f}"
            )


@contextmanager
def track_performance(name: str, threshold_ms: float = 100.0):
    """Context manager for tracking performance."""
    with PerformanceMonitor(name, threshold_ms):
        yield


def get_performance_logger() -> logging.Logger:
    """Get performance logger instance."""
    return _perf_logger
