"""任务数据结构 - OLP/Infer/Calc 阶段任务定义"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, TypeVar, Type

T = TypeVar("T")


@dataclass
class OlpTask:
    """OLP stage input task."""

    path: str
    source_batch: int = -1
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "source_batch": self.source_batch,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OlpTask":
        return cls(
            path=d["path"],
            source_batch=d.get("source_batch", -1),
            retry_count=d.get("retry_count", 0),
        )


@dataclass
class InferTask:
    """Infer stage input task (OLP output)."""

    path: str
    scf_path: str
    source_batch: int = -1
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "scf_path": self.scf_path,
            "source_batch": self.source_batch,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InferTask":
        return cls(
            path=d["path"],
            scf_path=d["scf_path"],
            source_batch=d.get("source_batch", -1),
            retry_count=d.get("retry_count", 0),
        )


@dataclass
class CalcTask:
    """Calc stage input task (Infer output)."""

    path: str
    geth_path: str
    scf_path: str = ""
    source_batch: int = -1
    retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "geth_path": self.geth_path,
            "scf_path": self.scf_path,
            "source_batch": self.source_batch,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CalcTask":
        return cls(
            path=d["path"],
            geth_path=d["geth_path"],
            scf_path=d.get("scf_path", ""),
            source_batch=d.get("source_batch", -1),
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
    from dlazy.utils.concurrency import atomic_append_jsonl
    import os

    if append:
        atomic_append_jsonl(filepath, records)
    else:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp_path), str(filepath))
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise


def read_tasks(filepath: Path, task_cls: Type[T]) -> List[T]:
    """Read tasks from JSON Lines file."""
    return [task_cls.from_dict(d) for d in _read_jsonl(filepath)]


def write_tasks(filepath: Path, tasks: List, append: bool = False) -> None:
    """Write tasks to JSON Lines file."""
    _write_jsonl(filepath, [t.to_dict() for t in tasks], append=append)


def read_olp_tasks(filepath: Path) -> List[OlpTask]:
    """Read OLP tasks from JSON Lines file."""
    return read_tasks(filepath, OlpTask)


def write_olp_tasks(filepath: Path, tasks: List[OlpTask]) -> None:
    """Write OLP tasks to JSON Lines file."""
    write_tasks(filepath, tasks)


def append_olp_task(filepath: Path, task: OlpTask) -> None:
    """Append a single OLP task."""
    write_tasks(filepath, [task], append=True)


def read_infer_tasks(filepath: Path) -> List[InferTask]:
    """Read Infer tasks from JSON Lines file."""
    return read_tasks(filepath, InferTask)


def write_infer_tasks(filepath: Path, tasks: List[InferTask]) -> None:
    """Write Infer tasks to JSON Lines file."""
    write_tasks(filepath, tasks)


def append_infer_task(filepath: Path, task: InferTask) -> None:
    """Append a single Infer task."""
    write_tasks(filepath, [task], append=True)


def read_calc_tasks(filepath: Path) -> List[CalcTask]:
    """Read Calc tasks from JSON Lines file."""
    return read_tasks(filepath, CalcTask)


def write_calc_tasks(filepath: Path, tasks: List[CalcTask]) -> None:
    """Write Calc tasks to JSON Lines file."""
    write_tasks(filepath, tasks)


def append_calc_task(filepath: Path, task: CalcTask) -> None:
    """Append a single Calc task."""
    write_tasks(filepath, [task], append=True)


def count_tasks(filepath: Path) -> int:
    """Count lines in a JSONL file."""
    if not filepath.exists():
        return 0
    return sum(1 for _ in _read_jsonl(filepath))
