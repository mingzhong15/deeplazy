# Batch Workflow Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement batch iterative computation for large-scale structure calculations with unified JSON Lines format and flattened directory structure.

**Architecture:** Add BatchWorkflowManager that orchestrates batch execution, reusing existing three-stage (OLP→Infer→Calc) logic. Simplify directory structure to task.NNNNNN/{olp,infer,scf}/ pattern. Unify task records to JSON Lines format.

**Tech Stack:** Python 3.8+, dataclasses, JSON Lines, pathlib

---

## File Structure

### New Files
- `deeplazy/record_utils.py` - Unified record format read/write functions
- `deeplazy/batch_workflow.py` - BatchWorkflowManager class
- `tests/test_record_utils.py` - Tests for record utilities
- `tests/test_batch_workflow.py` - Tests for batch workflow

### Modified Files
- `deeplazy/constants.py` - Add new filename constants
- `deeplazy/contexts.py` - Add BatchContext, simplify stage contexts
- `deeplazy/executor.py` - Adapt to new record format and directory structure
- `deeplazy/commands.py` - Write to new format, use deterministic task paths
- `deeplazy/cli.py` - Add --batch-size, --resume parameters
- `deeplazy/utils.py` - Remove generate_random_paths, simplify MaterialRecord
- `deeplazy/workflow.py` - Minor adjustments for compatibility

---

## Chunk 1: Record Utilities and Constants

### Task 1.1: Add Constants

**Files:**
- Modify: `deeplazy/constants.py`

- [ ] **Step 1: Add new filename constants**

```python
# At the end of constants.py

# ============================================
# Unified Record Files (JSON Lines)
# ============================================
OLP_TASKS_FILE = "olp_tasks.jsonl"
INFER_TASKS_FILE = "infer_tasks.jsonl"
CALC_TASKS_FILE = "calc_tasks.jsonl"
ERROR_TASKS_FILE = "error_tasks.jsonl"

# ============================================
# Batch State
# ============================================
BATCH_STATE_FILE = "batch_state.json"
BATCH_DIR_PREFIX = "batch"
BATCH_PADDING = 5
TASK_DIR_PREFIX = "task"
TASK_PADDING = 6

# ============================================
# Stage Subdirectories (within task dir)
# ============================================
OLP_SUBDIR = "olp"
INFER_SUBDIR = "infer"
SCF_SUBDIR = "scf"
```

- [ ] **Step 2: Verify constants load correctly**

Run: `python -c "from deeplazy.constants import OLP_TASKS_FILE, BATCH_STATE_FILE; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add deeplazy/constants.py
git commit -m "feat: add batch workflow constants"
```

---

### Task 1.2: Create Record Utilities

**Files:**
- Create: `deeplazy/record_utils.py`
- Create: `tests/test_record_utils.py`

- [ ] **Step 1: Write failing tests for record utilities**

```python
# tests/test_record_utils.py
import json
import tempfile
from pathlib import Path

from deeplazy.record_utils import (
    read_olp_tasks,
    write_olp_tasks,
    read_infer_tasks,
    write_infer_tasks,
    read_calc_tasks,
    write_calc_tasks,
    append_error_task,
    OlpTask,
    InferTask,
    CalcTask,
    ErrorTask,
)


class TestOlpTask:
    def test_olp_task_creation(self):
        task = OlpTask(poscar_path="/path/to/POSCAR")
        assert task.poscar_path == "/path/to/POSCAR"

    def test_olp_task_to_dict(self):
        task = OlpTask(poscar_path="/path/to/POSCAR")
        assert task.to_dict() == {"poscar_path": "/path/to/POSCAR"}

    def test_read_write_olp_tasks(self):
        tasks = [
            OlpTask(poscar_path="/path/a.vasp"),
            OlpTask(poscar_path="/path/b.vasp"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "olp_tasks.jsonl"
            write_olp_tasks(filepath, tasks)
            assert filepath.exists()
            
            loaded = read_olp_tasks(filepath)
            assert len(loaded) == 2
            assert loaded[0].poscar_path == "/path/a.vasp"
            assert loaded[1].poscar_path == "/path/b.vasp"


class TestInferTask:
    def test_infer_task_creation(self):
        task = InferTask(
            poscar_path="/path/to/POSCAR",
            scf_path="batch.00000/task.000000/olp",
        )
        assert task.poscar_path == "/path/to/POSCAR"
        assert task.scf_path == "batch.00000/task.000000/olp"

    def test_read_write_infer_tasks(self):
        tasks = [
            InferTask(poscar_path="/a.vasp", scf_path="batch.0/task.0/olp"),
            InferTask(poscar_path="/b.vasp", scf_path="batch.0/task.1/olp"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "infer_tasks.jsonl"
            write_infer_tasks(filepath, tasks)
            loaded = read_infer_tasks(filepath)
            assert len(loaded) == 2


class TestCalcTask:
    def test_calc_task_creation(self):
        task = CalcTask(
            poscar_path="/path/to/POSCAR",
            geth_path="batch.00000/task.000000/infer",
        )
        assert task.geth_path == "batch.00000/task.000000/infer"

    def test_read_write_calc_tasks(self):
        tasks = [
            CalcTask(poscar_path="/a.vasp", geth_path="batch.0/task.0/infer"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "calc_tasks.jsonl"
            write_calc_tasks(filepath, tasks)
            loaded = read_calc_tasks(filepath)
            assert len(loaded) == 1


class TestErrorTask:
    def test_error_task_creation(self):
        task = ErrorTask(
            poscar_path="/path/to/POSCAR",
            stage="olp",
            error="openmx failed",
            batch_id="00000",
            task_id="000000",
        )
        assert task.stage == "olp"
        assert task.error == "openmx failed"

    def test_append_error_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "error_tasks.jsonl"
            append_error_task(filepath, ErrorTask(
                poscar_path="/a.vasp",
                stage="olp",
                error="err1",
                batch_id="0",
                task_id="0",
            ))
            append_error_task(filepath, ErrorTask(
                poscar_path="/b.vasp",
                stage="infer",
                error="err2",
                batch_id="0",
                task_id="1",
            ))
            with open(filepath) as f:
                lines = f.readlines()
            assert len(lines) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .worktrees/batch-workflow && python -m pytest tests/test_record_utils.py -v`
Expected: FAIL with module import errors

- [ ] **Step 3: Implement record utilities**

```python
# deeplazy/record_utils.py
"""Unified record format utilities for batch workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Iterator


@dataclass
class OlpTask:
    """OLP stage input task."""
    poscar_path: str

    def to_dict(self) -> dict:
        return {"poscar_path": self.poscar_path}

    @classmethod
    def from_dict(cls, d: dict) -> "OlpTask":
        return cls(poscar_path=d["poscar_path"])


@dataclass
class InferTask:
    """Infer stage input task (OLP output)."""
    poscar_path: str
    scf_path: str

    def to_dict(self) -> dict:
        return {"poscar_path": self.poscar_path, "scf_path": self.scf_path}

    @classmethod
    def from_dict(cls, d: dict) -> "InferTask":
        return cls(poscar_path=d["poscar_path"], scf_path=d["scf_path"])


@dataclass
class CalcTask:
    """Calc stage input task (Infer output)."""
    poscar_path: str
    geth_path: str

    def to_dict(self) -> dict:
        return {"poscar_path": self.poscar_path, "geth_path": self.geth_path}

    @classmethod
    def from_dict(cls, d: dict) -> "CalcTask":
        return cls(poscar_path=d["poscar_path"], geth_path=d["geth_path"])


@dataclass
class ErrorTask:
    """Failed task record."""
    poscar_path: str
    stage: str
    error: str
    batch_id: str
    task_id: str

    def to_dict(self) -> dict:
        return {
            "poscar_path": self.poscar_path,
            "stage": self.stage,
            "error": self.error,
            "batch_id": self.batch_id,
            "task_id": self.task_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ErrorTask":
        return cls(
            poscar_path=d["poscar_path"],
            stage=d["stage"],
            error=d["error"],
            batch_id=d["batch_id"],
            task_id=d["task_id"],
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .worktrees/batch-workflow && python -m pytest tests/test_record_utils.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add deeplazy/record_utils.py tests/test_record_utils.py
git commit -m "feat: add unified record format utilities"
```

---

## Chunk 2: Path Utilities Refactoring

### Task 2.1: Simplify Path Generation

**Files:**
- Modify: `deeplazy/utils.py`

- [ ] **Step 1: Write tests for new path utilities**

```python
# Add to tests/test_record_utils.py or create tests/test_path_utils.py

from deeplazy.utils import get_task_dir, get_batch_dir


class TestPathUtils:
    def test_get_batch_dir(self):
        from pathlib import Path
        root = Path("/workflow")
        batch_dir = get_batch_dir(root, 0)
        assert batch_dir == Path("/workflow/batch.00000")
        
        batch_dir = get_batch_dir(root, 42)
        assert batch_dir == Path("/workflow/batch.00042")

    def test_get_task_dir(self):
        from pathlib import Path
        batch_dir = Path("/workflow/batch.00000")
        task_dir = get_task_dir(batch_dir, 0)
        assert task_dir == Path("/workflow/batch.00000/task.000000")
        
        task_dir = get_task_dir(batch_dir, 123)
        assert task_dir == Path("/workflow/batch.00000/task.000123")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd .worktrees/batch-workflow && python -m pytest tests/test_path_utils.py -v 2>/dev/null || echo "Expected to fail"`

- [ ] **Step 3: Add new path utilities and remove generate_random_paths**

Add to `deeplazy/utils.py`:

```python
from .constants import (
    # ... existing imports ...
    BATCH_DIR_PREFIX,
    BATCH_PADDING,
    TASK_DIR_PREFIX,
    TASK_PADDING,
)


def get_batch_dir(workflow_root: Path, batch_index: int) -> Path:
    """Get batch directory path."""
    return workflow_root / f"{BATCH_DIR_PREFIX}.{batch_index:0{BATCH_PADDING}d}"


def get_task_dir(batch_dir: Path, task_index: int) -> Path:
    """Get task directory path within a batch."""
    return batch_dir / f"{TASK_DIR_PREFIX}.{task_index:0{TASK_PADDING}d}"
```

Then **remove** the `generate_random_paths` function (lines 348-357).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd .worktrees/batch-workflow && python -m pytest tests/test_path_utils.py -v`

- [ ] **Step 5: Commit**

```bash
git add deeplazy/utils.py tests/test_path_utils.py
git commit -m "refactor: replace random paths with deterministic task directories"
```

---

### Task 2.2: Simplify MaterialRecord

**Files:**
- Modify: `deeplazy/utils.py`

- [ ] **Step 1: Simplify MaterialRecord dataclass**

Remove the `short_path` property from `MaterialRecord` class.

- [ ] **Step 2: Verify existing code still works**

Run: `cd .worktrees/batch-workflow && python -c "from deeplazy.utils import MaterialRecord; r = MaterialRecord('label', '/scf', '/geth'); print(r.label)"`

- [ ] **Step 3: Commit**

```bash
git add deeplazy/utils.py
git commit -m "refactor: simplify MaterialRecord, remove short_path"
```

---

## Chunk 3: Context Updates

### Task 3.1: Add BatchContext and Update Stage Contexts

**Files:**
- Modify: `deeplazy/contexts.py`

- [ ] **Step 1: Add BatchContext and update existing contexts**

```python
# deeplazy/contexts.py
"""Execution context definitions."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional


@dataclass
class BaseContext:
    """Base context."""
    config: Dict[str, Any]
    workflow_root: Path
    workdir: Path


@dataclass
class BatchContext:
    """Batch workflow context."""
    config_path: Path
    workflow_root: Path
    batch_size: int
    resume: bool = False
    state_file: Optional[Path] = None
    olp_tasks_file: Optional[Path] = None
    infer_tasks_file: Optional[Path] = None
    calc_tasks_file: Optional[Path] = None
    error_tasks_file: Optional[Path] = None


@dataclass
class OLPContext(BaseContext):
    """OLP stage context."""
    batch_id: str
    batch_dir: Path
    error_file: Path
    num_cores: int = 64
    max_processes: int = 8


@dataclass
class InferContext(BaseContext):
    """Infer stage context."""
    batch_id: str
    batch_dir: Path
    error_file: Path
    hamlog_file: Path
    group_info_file: Path
    num_groups: int = 10
    random_seed: int = 137
    parallel: int = 56
    model_dir: Path = Path("/path/to/model")
    dataset_prefix: str = "dataset"


@dataclass
class CalcContext(BaseContext):
    """Calc stage context."""
    batch_id: str
    batch_dir: Path
    error_file: Path
    folders_file: Path
    hamlog_file: Path
```

- [ ] **Step 2: Verify imports work**

Run: `cd .worktrees/batch-workflow && python -c "from deeplazy.contexts import BatchContext, OLPContext; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add deeplazy/contexts.py
git commit -m "feat: add BatchContext and update stage contexts for batch workflow"
```

---

## Chunk 4: Commands Refactoring

### Task 4.1: Refactor OLP Command Executor

**Files:**
- Modify: `deeplazy/commands.py`

- [ ] **Step 1: Add batch-mode OLP execution method**

Key changes:
1. Accept `task_index` and `poscar_path`
2. Create deterministic task directory: `{batch_dir}/task.{NNNNNN}/olp/`
3. Write results to `overlaps.h5` in the olp directory
4. Return InferTask for the output

- [ ] **Step 2: Keep old execute method for backward compatibility**

Don't remove the old `execute` method, add `execute_batch` as new method.

- [ ] **Step 3: Commit**

```bash
git add deeplazy/commands.py
git commit -m "feat: add batch-mode OLP execution with deterministic paths"
```

---

### Task 4.2: Refactor Infer Command Executor

**Files:**
- Modify: `deeplazy/commands.py`

- [ ] **Step 1: Add batch-mode Infer execution**

Similar pattern to OLP:
- Read InferTasks from `batch_dir/infer_tasks.jsonl`
- Create `task_dir/infer/` directory
- Process within batch
- Output CalcTasks

- [ ] **Step 2: Commit**

```bash
git add deeplazy/commands.py
git commit -m "feat: add batch-mode Infer execution"
```

---

### Task 4.3: Refactor Calc Command Executor

**Files:**
- Modify: `deeplazy/commands.py`

- [ ] **Step 1: Add batch-mode Calc execution**

- Read CalcTasks from `batch_dir/calc_tasks.jsonl`
- Create `task_dir/scf/` directory
- Run OpenMX restart from predicted Hamiltonian
- Output final Hamiltonian

- [ ] **Step 2: Commit**

```bash
git add deeplazy/commands.py
git commit -m "feat: add batch-mode Calc execution"
```

---

## Chunk 5: BatchWorkflowManager

### Task 5.1: Create BatchWorkflowManager Core

**Files:**
- Create: `deeplazy/batch_workflow.py`
- Create: `tests/test_batch_workflow.py`

- [ ] **Step 1: Write BatchWorkflowManager skeleton with state management**

- [ ] **Step 2: Implement batch preparation and result merging**

- [ ] **Step 3: Implement batch stage execution methods**

- [ ] **Step 4: Write basic tests**

- [ ] **Step 5: Commit**

```bash
git add deeplazy/batch_workflow.py tests/test_batch_workflow.py
git commit -m "feat: add BatchWorkflowManager implementation"
```

---

## Chunk 6: CLI Integration

### Task 6.1: Add CLI Commands

**Files:**
- Modify: `deeplazy/cli.py`

- [ ] **Step 1: Add --batch-size and --resume arguments**

- [ ] **Step 2: Update cmd_run to support batch mode**

- [ ] **Step 3: Add batch-status command**

- [ ] **Step 4: Test CLI**

- [ ] **Step 5: Commit**

```bash
git add deeplazy/cli.py
git commit -m "feat: add --batch-size and --resume CLI arguments"
```

---

## Chunk 7: Documentation and Final Testing

### Task 7.1: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add batch workflow documentation**

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add batch workflow documentation"
```

---

### Task 7.2: Final Integration Test

- [ ] **Step 1: Run full test suite**

- [ ] **Step 2: Manual smoke test**

- [ ] **Step 3: Verify backward compatibility**

- [ ] **Step 4: Final commit**

---

## Summary

| Chunk | Description | Files Changed |
|-------|-------------|---------------|
| 1 | Record utilities & constants | constants.py, record_utils.py, tests/test_record_utils.py |
| 2 | Path utilities refactoring | utils.py, tests/test_path_utils.py |
| 3 | Context updates | contexts.py |
| 4 | Commands refactoring | commands.py |
| 5 | BatchWorkflowManager | batch_workflow.py, tests/test_batch_workflow.py |
| 6 | CLI integration | cli.py |
| 7 | Documentation | README.md |
