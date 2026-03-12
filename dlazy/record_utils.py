"""Unified record format utilities for batch workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List


@dataclass
class OlpTask:
    """OLP stage input task."""

    path: str

    def to_dict(self) -> dict:
        return {"path": self.path}

    @classmethod
    def from_dict(cls, d: dict) -> "OlpTask":
        return cls(path=d["path"])


@dataclass
class InferTask:
    """Infer stage input task (OLP output)."""

    path: str
    scf_path: str

    def to_dict(self) -> dict:
        return {"path": self.path, "scf_path": self.scf_path}

    @classmethod
    def from_dict(cls, d: dict) -> "InferTask":
        return cls(path=d["path"], scf_path=d["scf_path"])


@dataclass
class CalcTask:
    """Calc stage input task (Infer output)."""

    path: str
    geth_path: str

    def to_dict(self) -> dict:
        return {"path": self.path, "geth_path": self.geth_path}

    @classmethod
    def from_dict(cls, d: dict) -> "CalcTask":
        return cls(path=d["path"], geth_path=d["geth_path"])


@dataclass
class ErrorTask:
    """Failed task record."""

    path: str
    stage: str
    error: str
    batch_id: str
    task_id: str
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "stage": self.stage,
            "error": self.error,
            "batch_id": self.batch_id,
            "task_id": self.task_id,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ErrorTask":
        return cls(
            path=d["path"],
            stage=d["stage"],
            error=d["error"],
            batch_id=d["batch_id"],
            task_id=d["task_id"],
            retry_count=d.get("retry_count", 0),
        )


def _read_jsonl(filepath: Path) -> Iterator[dict]:
    """Read JSON Lines file."""
    if not filepath.exists():
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def _write_jsonl(filepath: Path, records: List[dict], append: bool = False) -> None:
    """Write records to JSON Lines file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(filepath, mode, encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_olp_tasks(filepath: Path) -> List[OlpTask]:
    """Read OLP tasks from JSON Lines file."""
    return [OlpTask.from_dict(d) for d in _read_jsonl(filepath)]


def write_olp_tasks(filepath: Path, tasks: List[OlpTask]) -> None:
    """Write OLP tasks to JSON Lines file."""
    _write_jsonl(filepath, [t.to_dict() for t in tasks])


def read_infer_tasks(filepath: Path) -> List[InferTask]:
    """Read Infer tasks from JSON Lines file."""
    return [InferTask.from_dict(d) for d in _read_jsonl(filepath)]


def write_infer_tasks(filepath: Path, tasks: List[InferTask]) -> None:
    """Write Infer tasks to JSON Lines file."""
    _write_jsonl(filepath, [t.to_dict() for t in tasks])


def append_infer_task(filepath: Path, task: InferTask) -> None:
    """Append a single Infer task."""
    _write_jsonl(filepath, [task.to_dict()], append=True)


def read_calc_tasks(filepath: Path) -> List[CalcTask]:
    """Read Calc tasks from JSON Lines file."""
    return [CalcTask.from_dict(d) for d in _read_jsonl(filepath)]


def write_calc_tasks(filepath: Path, tasks: List[CalcTask]) -> None:
    """Write Calc tasks to JSON Lines file."""
    _write_jsonl(filepath, [t.to_dict() for t in tasks])


def append_calc_task(filepath: Path, task: CalcTask) -> None:
    """Append a single Calc task."""
    _write_jsonl(filepath, [task.to_dict()], append=True)


def append_error_task(filepath: Path, task: ErrorTask) -> None:
    """Append an error task."""
    _write_jsonl(filepath, [task.to_dict()], append=True)


def append_olp_task(filepath: Path, task: OlpTask) -> None:
    """Append a single OLP task."""
    _write_jsonl(filepath, [task.to_dict()], append=True)


def count_tasks(filepath: Path) -> int:
    """Count lines in a JSONL file."""
    if not filepath.exists():
        return 0
    return sum(1 for _ in _read_jsonl(filepath))


def get_task_retry_count(workflow_root: Path, task_path: str) -> int:
    """Count how many times a task has failed across all batches."""
    count = 0
    batch_dirs = sorted(workflow_root.glob("batch.*"))
    for batch_dir in batch_dirs:
        error_files = list(batch_dir.rglob("error_tasks.jsonl"))
        for ef in error_files:
            for d in _read_jsonl(ef):
                if d.get("path") == task_path:
                    count += 1
    return count
