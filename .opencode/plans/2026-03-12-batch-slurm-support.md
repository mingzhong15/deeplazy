# Batch Workflow SLURM Support Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SLURM job submission support for `dlazy batch` command, enabling iterative batch processing with automatic job scheduling.

**Architecture:** Introduce `PathResolver` abstraction to unify file path resolution between `run` and `batch` modes. `BatchScheduler` manages the batch loop and stage progression, reusing existing `WorkflowExecutor` and SLURM script generation logic.

**Tech Stack:** Python 3.8+, dataclasses, subprocess, pathlib

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `dlazy/path_resolver.py` | Create | PathResolver base class, RunPathResolver, BatchPathResolver |
| `dlazy/constants.py` | Modify | Add batch-related constants |
| `dlazy/executor.py` | Modify | Accept PathResolver parameter |
| `dlazy/batch_workflow.py` | Rewrite | Simplify to BatchScheduler (loop + stage management) |
| `dlazy/workflow.py` | Modify | Use RunPathResolver |
| `dlazy/cli.py` | Modify | cmd_batch() calls BatchScheduler |
| `tests/test_path_resolver.py` | Create | Unit tests for PathResolver |
| `tests/test_batch_scheduler.py` | Create | Unit tests for BatchScheduler |

---

## Chunk 1: PathResolver Implementation

### Task 1: Add Batch Constants

**Files:**
- Modify: `dlazy/constants.py:80-93`

- [ ] **Step 1: Add batch stage constants to constants.py**

Add after line 79 (after `SCF_SUBDIR = "scf"`):

```python
# ============================================
# Batch Workflow Stages
# ============================================
BATCH_STAGES = ["olp", "infer", "calc"]
BATCH_STAGE_CONFIG_MAP = {
    "olp": "0olp",
    "infer": "1infer",
    "calc": "2calc",
}
BATCH_JOB_NAMES = {
    "olp": "B-batch-olp",
    "infer": "B-batch-infer",
    "calc": "B-batch-calc",
}

# Batch subdirectory templates
SLURM_SUBDIR_TEMPLATE = "slurm_{}"      # slurm_olp, slurm_infer, slurm_calc
OUTPUT_SUBDIR_TEMPLATE = "output_{}"    # output_olp, output_infer, output_calc
```

- [ ] **Step 2: Verify constants are importable**

Run: `python -c "from dlazy.constants import BATCH_STAGES, BATCH_STAGE_CONFIG_MAP, BATCH_JOB_NAMES, SLURM_SUBDIR_TEMPLATE, OUTPUT_SUBDIR_TEMPLATE; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add dlazy/constants.py
git commit -m "feat(constants): add batch workflow stage constants"
```

---

### Task 2: Create PathResolver Base Class

**Files:**
- Create: `dlazy/path_resolver.py`
- Create: `tests/test_path_resolver.py`

- [ ] **Step 1: Write failing test for PathResolver base class**

Create `tests/test_path_resolver.py`:

```python
"""Tests for PathResolver."""

from pathlib import Path
import pytest

from dlazy.path_resolver import PathResolver, RunPathResolver, BatchPathResolver


class TestPathResolverBase:
    """Tests for PathResolver base class."""

    def test_is_abstract(self):
        """PathResolver should be abstract and not instantiable."""
        with pytest.raises(TypeError):
            PathResolver()


class TestRunPathResolver:
    """Tests for RunPathResolver."""

    def test_olp_paths(self, tmp_path):
        """Test OLP stage paths in run mode."""
        resolver = RunPathResolver(tmp_path)
        
        assert resolver.get_olp_slurm_dir() == tmp_path / "0olp"
        assert resolver.get_olp_output_dir() == tmp_path / "0olp"
        assert resolver.get_olp_tasks_file() == tmp_path / "0olp" / "olp_tasks.jsonl"
        assert resolver.get_olp_error_file() == tmp_path / "0olp" / "error_tasks.jsonl"
        assert resolver.get_olp_folders_file() == tmp_path / "0olp" / "folders.dat"

    def test_infer_paths(self, tmp_path):
        """Test Infer stage paths in run mode."""
        resolver = RunPathResolver(tmp_path)
        
        assert resolver.get_infer_slurm_dir() == tmp_path / "1infer"
        assert resolver.get_infer_output_dir() == tmp_path / "1infer"
        assert resolver.get_infer_tasks_file() == tmp_path / "1infer" / "infer_tasks.jsonl"
        assert resolver.get_infer_input_source() == tmp_path / "0olp" / "folders.dat"
        assert resolver.get_infer_hamlog_file() == tmp_path / "1infer" / "hamlog.dat"

    def test_calc_paths(self, tmp_path):
        """Test Calc stage paths in run mode."""
        resolver = RunPathResolver(tmp_path)
        
        assert resolver.get_calc_slurm_dir() == tmp_path / "2calc"
        assert resolver.get_calc_output_dir() == tmp_path / "2calc"
        assert resolver.get_calc_tasks_file() == tmp_path / "2calc" / "calc_tasks.jsonl"
        assert resolver.get_calc_input_source() == tmp_path / "1infer" / "hamlog.dat"


class TestBatchPathResolver:
    """Tests for BatchPathResolver."""

    def test_batch_olp_paths(self, tmp_path):
        """Test OLP stage paths in batch mode."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)
        
        assert resolver.get_olp_slurm_dir() == tmp_path / "batch.00000" / "slurm_olp"
        assert resolver.get_olp_output_dir() == tmp_path / "batch.00000" / "output_olp"
        assert resolver.get_olp_tasks_file() == tmp_path / "batch.00000" / "slurm_olp" / "olp_tasks.jsonl"

    def test_batch_infer_paths(self, tmp_path):
        """Test Infer stage paths in batch mode."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)
        
        assert resolver.get_infer_slurm_dir() == tmp_path / "batch.00000" / "slurm_infer"
        assert resolver.get_infer_output_dir() == tmp_path / "batch.00000" / "output_infer"
        assert resolver.get_infer_input_source() == tmp_path / "batch.00000" / "output_olp" / "folders.dat"

    def test_batch_calc_paths(self, tmp_path):
        """Test Calc stage paths in batch mode."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)
        
        assert resolver.get_calc_slurm_dir() == tmp_path / "batch.00000" / "slurm_calc"
        assert resolver.get_calc_output_dir() == tmp_path / "batch.00000" / "output_calc"
        assert resolver.get_calc_input_source() == tmp_path / "batch.00000" / "output_infer" / "hamlog.dat"

    def test_batch_index_padding(self, tmp_path):
        """Test batch index is zero-padded."""
        resolver = BatchPathResolver(tmp_path, batch_index=42)
        
        assert "batch.00042" in str(resolver.get_olp_slurm_dir())

    def test_get_todo_list_file(self, tmp_path):
        """Test todo_list.json path."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)
        
        assert resolver.get_todo_list_file() == tmp_path / "todo_list.json"

    def test_get_next_batch_resolver(self, tmp_path):
        """Test getting next batch resolver."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)
        next_resolver = resolver.get_next_batch_resolver()
        
        assert next_resolver._batch_index == 1
        assert "batch.00001" in str(next_resolver.get_olp_slurm_dir())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_path_resolver.py -v`

Expected: FAIL with "No module named 'dlazy.path_resolver'"

- [ ] **Step 3: Create PathResolver implementation**

Create `dlazy/path_resolver.py`:

```python
"""Path resolver for unified file path resolution between run and batch modes."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import (
    FOLDERS_FILE,
    HAMLOG_FILE,
    PROGRESS_FILE,
    OLP_TASKS_FILE,
    INFER_TASKS_FILE,
    CALC_TASKS_FILE,
    ERROR_TASKS_FILE,
    BATCH_DIR_PREFIX,
    BATCH_PADDING,
    SLURM_SUBDIR_TEMPLATE,
    OUTPUT_SUBDIR_TEMPLATE,
)

if TYPE_CHECKING:
    pass


class PathResolver(ABC):
    """Base class for path resolution."""

    @abstractmethod
    def get_workdir(self) -> Path:
        """Get working directory."""
        pass

    # ========== OLP Stage ==========

    @abstractmethod
    def get_olp_slurm_dir(self) -> Path:
        """Get OLP SLURM script directory."""
        pass

    @abstractmethod
    def get_olp_output_dir(self) -> Path:
        """Get OLP output directory."""
        pass

    def get_olp_tasks_file(self) -> Path:
        """Get OLP tasks file."""
        return self.get_olp_slurm_dir() / OLP_TASKS_FILE

    def get_olp_error_file(self) -> Path:
        """Get OLP error tasks file."""
        return self.get_olp_slurm_dir() / ERROR_TASKS_FILE

    def get_olp_progress_file(self) -> Path:
        """Get OLP progress file."""
        return self.get_olp_slurm_dir() / PROGRESS_FILE

    def get_olp_folders_file(self) -> Path:
        """Get OLP folders.dat file."""
        return self.get_olp_output_dir() / FOLDERS_FILE

    # ========== Infer Stage ==========

    @abstractmethod
    def get_infer_slurm_dir(self) -> Path:
        """Get Infer SLURM script directory."""
        pass

    @abstractmethod
    def get_infer_output_dir(self) -> Path:
        """Get Infer output directory."""
        pass

    def get_infer_tasks_file(self) -> Path:
        """Get Infer tasks file."""
        return self.get_infer_slurm_dir() / INFER_TASKS_FILE

    def get_infer_error_file(self) -> Path:
        """Get Infer error tasks file."""
        return self.get_infer_slurm_dir() / ERROR_TASKS_FILE

    def get_infer_input_source(self) -> Path:
        """Get Infer input source (from OLP output)."""
        return self.get_olp_folders_file()

    def get_infer_hamlog_file(self) -> Path:
        """Get Infer hamlog.dat file."""
        return self.get_infer_output_dir() / HAMLOG_FILE

    # ========== Calc Stage ==========

    @abstractmethod
    def get_calc_slurm_dir(self) -> Path:
        """Get Calc SLURM script directory."""
        pass

    @abstractmethod
    def get_calc_output_dir(self) -> Path:
        """Get Calc output directory."""
        pass

    def get_calc_tasks_file(self) -> Path:
        """Get Calc tasks file."""
        return self.get_calc_slurm_dir() / CALC_TASKS_FILE

    def get_calc_error_file(self) -> Path:
        """Get Calc error tasks file."""
        return self.get_calc_slurm_dir() / ERROR_TASKS_FILE

    def get_calc_progress_file(self) -> Path:
        """Get Calc progress file."""
        return self.get_calc_slurm_dir() / PROGRESS_FILE

    def get_calc_folders_file(self) -> Path:
        """Get Calc folders.dat file."""
        return self.get_calc_output_dir() / FOLDERS_FILE

    def get_calc_input_source(self) -> Path:
        """Get Calc input source (from Infer output)."""
        return self.get_infer_hamlog_file()


class RunPathResolver(PathResolver):
    """Path resolver for 'dlazy run' mode."""

    def __init__(self, workdir: Path):
        self._workdir = Path(workdir).resolve()

    def get_workdir(self) -> Path:
        return self._workdir

    def get_olp_slurm_dir(self) -> Path:
        return self._workdir / "0olp"

    def get_olp_output_dir(self) -> Path:
        return self._workdir / "0olp"

    def get_infer_slurm_dir(self) -> Path:
        return self._workdir / "1infer"

    def get_infer_output_dir(self) -> Path:
        return self._workdir / "1infer"

    def get_calc_slurm_dir(self) -> Path:
        return self._workdir / "2calc"

    def get_calc_output_dir(self) -> Path:
        return self._workdir / "2calc"


class BatchPathResolver(PathResolver):
    """Path resolver for 'dlazy batch' mode."""

    def __init__(self, workflow_root: Path, batch_index: int):
        self._workflow_root = Path(workflow_root).resolve()
        self._batch_index = batch_index
        self._batch_dir = self._workflow_root / f"{BATCH_DIR_PREFIX}.{batch_index:0{BATCH_PADDING}d}"

    def get_workdir(self) -> Path:
        return self._batch_dir

    def get_olp_slurm_dir(self) -> Path:
        return self._batch_dir / SLURM_SUBDIR_TEMPLATE.format("olp")

    def get_olp_output_dir(self) -> Path:
        return self._batch_dir / OUTPUT_SUBDIR_TEMPLATE.format("olp")

    def get_infer_slurm_dir(self) -> Path:
        return self._batch_dir / SLURM_SUBDIR_TEMPLATE.format("infer")

    def get_infer_output_dir(self) -> Path:
        return self._batch_dir / OUTPUT_SUBDIR_TEMPLATE.format("infer")

    def get_calc_slurm_dir(self) -> Path:
        return self._batch_dir / SLURM_SUBDIR_TEMPLATE.format("calc")

    def get_calc_output_dir(self) -> Path:
        return self._batch_dir / OUTPUT_SUBDIR_TEMPLATE.format("calc")

    # ========== Batch-specific methods ==========

    def get_todo_list_file(self) -> Path:
        """Get todo_list.json path at workflow root."""
        return self._workflow_root / "todo_list.json"

    def get_next_batch_resolver(self) -> "BatchPathResolver":
        """Get PathResolver for the next batch."""
        return BatchPathResolver(self._workflow_root, self._batch_index + 1)

    @property
    def batch_index(self) -> int:
        """Get current batch index."""
        return self._batch_index
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_path_resolver.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/path_resolver.py tests/test_path_resolver.py
git commit -m "feat(path_resolver): add PathResolver abstraction for run/batch modes"
```

---

### Task 3: Export PathResolver from __init__.py

**Files:**
- Modify: `dlazy/__init__.py`

- [ ] **Step 1: Add PathResolver exports**

Modify `dlazy/__init__.py`:

```python
"""工作流核心库"""

from .executor import WorkflowExecutor
from .contexts import OLPContext, InferContext, CalcContext, BatchContext
from .exceptions import (
    WorkflowError,
    ConfigError,
    NodeError,
    CalculationError,
    TransformError,
    InferError,
    GroupNotFoundError,
    HamiltonianNotFoundError,
    FailureType,
    AbortException,
)
from .path_resolver import PathResolver, RunPathResolver, BatchPathResolver

__version__ = "2.4.0"
__all__ = [
    "WorkflowExecutor",
    "OLPContext",
    "InferContext",
    "CalcContext",
    "BatchContext",
    "WorkflowError",
    "ConfigError",
    "NodeError",
    "CalculationError",
    "TransformError",
    "InferError",
    "GroupNotFoundError",
    "HamiltonianNotFoundError",
    "FailureType",
    "AbortException",
    "PathResolver",
    "RunPathResolver",
    "BatchPathResolver",
]
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from dlazy import PathResolver, RunPathResolver, BatchPathResolver; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add dlazy/__init__.py
git commit -m "feat: export PathResolver from package"
```

---

## Chunk 2: Executor Modification

### Task 4: Add PathResolver Support to WorkflowExecutor

**Files:**
- Modify: `dlazy/executor.py`

- [ ] **Step 1: Add import and modify run_olp_stage signature**

Add to imports in `dlazy/executor.py`:

```python
from .path_resolver import PathResolver, RunPathResolver
```

Modify `run_olp_stage` method signature:

```python
@staticmethod
def run_olp_stage(
    global_config: str,
    start: int,
    end: int,
    path_resolver: Optional[PathResolver] = None,
    workdir: Optional[str] = None,
    stru_log: Optional[str] = None,
    monitor: Optional[JobMonitor] = None,
) -> Dict[str, int]:
```

Update method body to use path_resolver:

```python
logger = get_logger("executor.olp")
logger.info("run_olp_stage: start=%d, end=%d", start, end)

config = load_global_config_section(Path(global_config), "0olp")

if path_resolver is None:
    path_resolver = RunPathResolver(Path(workdir) if workdir else Path.cwd())

workflow_root = path_resolver.get_workdir()
result_dir = path_resolver.get_olp_output_dir()

ctx = OLPContext(
    config=config,
    workflow_root=workflow_root,
    workdir=path_resolver.get_workdir(),
    result_dir=result_dir,
    progress_file=path_resolver.get_olp_progress_file(),
    folders_file=path_resolver.get_olp_folders_file(),
    error_file=path_resolver.get_olp_error_file(),
    num_cores=config.get("num_cores", 56),
    max_processes=config.get("max_processes", 7),
    node_error_flag=path_resolver.get_workdir() / f".node_error_flag-{secrets.token_hex(4)}",
    stru_log=Path(stru_log) if stru_log else None,
    monitor=monitor,
)
```

- [ ] **Step 2: Add PathResolver support to run_infer_stage**

Modify signature:

```python
@staticmethod
def run_infer_stage(
    global_config: str,
    group_index: int,
    path_resolver: Optional[PathResolver] = None,
    workdir: Optional[str] = None,
) -> Dict[str, Any]:
```

Update body similarly.

- [ ] **Step 3: Add PathResolver support to run_calc_stage**

Modify signature:

```python
@staticmethod
def run_calc_stage(
    global_config: str,
    start: int,
    end: int,
    path_resolver: Optional[PathResolver] = None,
    workdir: Optional[str] = None,
    stru_log: Optional[str] = None,
    monitor: Optional[JobMonitor] = None,
) -> Dict[str, int]:
```

Update body similarly.

- [ ] **Step 4: Verify executor still works with existing tests**

Run: `python -m pytest tests/ -v -k "not path_resolver and not batch_scheduler"`

Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/executor.py
git commit -m "feat(executor): add PathResolver parameter for run/batch mode unification"
```

---

## Chunk 3: BatchScheduler Implementation

### Task 5: Rewrite batch_workflow.py

**Files:**
- Rewrite: `dlazy/batch_workflow.py`
- Create: `tests/test_batch_scheduler.py`

- [ ] **Step 1: Write failing tests for BatchScheduler**

Create `tests/test_batch_scheduler.py` with tests for:
- `_load_or_init_state()`
- `_get_path_resolver()`
- `_has_more_batches()`
- `_get_next_stage()`
- State persistence

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_batch_scheduler.py -v`

Expected: FAIL

- [ ] **Step 3: Rewrite batch_workflow.py with BatchScheduler**

Implement:
- State management
- Path resolver integration
- Task preparation methods
- Stage status checking
- Job submission
- Main scheduling loop

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_batch_scheduler.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add dlazy/batch_workflow.py tests/test_batch_scheduler.py
git commit -m "feat(batch): rewrite BatchScheduler with PathResolver support"
```

---

## Chunk 4: CLI and Workflow Updates

### Task 6: Update CLI cmd_batch

**Files:**
- Modify: `dlazy/cli.py`

- [ ] **Step 1: Update cmd_batch to use BatchScheduler**

Replace the existing `cmd_batch` function to use `BatchScheduler` instead of `BatchWorkflowManager`.

- [ ] **Step 2: Verify CLI works**

Run: `python -m dlazy batch --help`

Expected: Shows batch command help

- [ ] **Step 3: Commit**

```bash
git add dlazy/cli.py
git commit -m "feat(cli): update cmd_batch to use BatchScheduler"
```

---

### Task 7: Update WorkflowManager to use RunPathResolver

**Files:**
- Modify: `dlazy/workflow.py`

- [ ] **Step 1: Add RunPathResolver import and initialize in __init__**

- [ ] **Step 2: Update _submit_job to use path_resolver**

- [ ] **Step 3: Verify existing tests pass**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add dlazy/workflow.py
git commit -m "feat(workflow): use RunPathResolver for path resolution"
```

---

### Task 8: Final Integration Test

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 2: Run linting**

Run: `ruff check dlazy/ tests/`

Expected: No errors

- [ ] **Step 3: Update version to 2.5.0**

- [ ] **Step 4: Update README.md with changelog**

- [ ] **Step 5: Final commit**

---

## Summary

This plan implements SLURM job submission support for `dlazy batch` by:

1. **Adding `PathResolver`** - Abstracts file path resolution between run/batch modes
2. **Modifying `WorkflowExecutor`** - Accepts PathResolver parameter  
3. **Rewriting `BatchScheduler`** - Manages batch loop with SLURM job submission
4. **Updating CLI** - cmd_batch() uses BatchScheduler

The design ensures:
- Core execution logic remains unchanged
- `dlazy run` and `dlazy batch` share the same underlying code
- Clear separation of concerns via PathResolver
- Full backward compatibility
