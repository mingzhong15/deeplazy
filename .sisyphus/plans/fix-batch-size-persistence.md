# Fix: Batch Size Persistence for Resume

## Problem

**`batch_size` is not saved in `batch_state.json`**, causing inconsistent batch sizes during retry.

### Scenario

```bash
# First run with custom batch-size
dlazy batch --config global_config.yaml --batch-size 50
# Creates: batch.00000 ~ batch.00013 (50 tasks each)

# Retry without specifying batch-size
dlazy batch-retry-tasks --config global_config.yaml --run
# Uses default 100, creates: batch.00014 (100 tasks)
# ❌ Inconsistent!
```

## Root Cause

State file (`batch_state.json`) does not include `batch_size`:

```json
{
  "current_batch": 7,
  "current_stage": "olp",
  "completed_batches": [],
  "initialized": false,
  "total_batches": 0,
  "start_batch_index": 8,
  "original_task_count": 704
  // Missing: "batch_size": 50
}
```

## Fix Plan

### Task 1: Save batch_size in state file

**File**: `dlazy/batch_workflow.py`

**Location**: `_load_or_init_state()` method, line ~115

**Change**:
```python
# Before
state = {
    "current_batch": start_batch,
    "current_stage": "olp",
    "completed_batches": [],
    "initialized": False,
    "total_batches": 0,
    "start_batch_index": start_batch,
    "original_task_count": original_task_count,
}

# After
state = {
    "current_batch": start_batch,
    "current_stage": "olp",
    "completed_batches": [],
    "initialized": False,
    "total_batches": 0,
    "start_batch_index": start_batch,
    "original_task_count": original_task_count,
    "batch_size": self.ctx.batch_size,  # ← NEW
}
```

### Task 2: Restore batch_size on retry

**File**: `dlazy/cli.py`

**Location**: `cmd_batch_retry_tasks()` function, line ~786

**Change**:
```python
# Before
ctx_run = BatchContext(
    config_path=config_path,
    workflow_root=workdir,
    batch_size=args.batch_size if args.batch_size else 100,
    fresh=False,
)

# After
# Read saved batch_size from state file
saved_batch_size = 100
state_file = workdir / "batch_state.json"
if state_file.exists():
    with open(state_file, "r") as f:
        saved_state = json.load(f)
        saved_batch_size = saved_state.get("batch_size", 100)

# Use explicit args.batch_size, otherwise use saved value
actual_batch_size = args.batch_size if args.batch_size else saved_batch_size

ctx_run = BatchContext(
    config_path=config_path,
    workflow_root=workdir,
    batch_size=actual_batch_size,
    fresh=False,
)
```

### Task 3: Add test case

**File**: `tests/test_batch_scheduler.py` (or create new)

**Test scenario**:
1. Run batch with `--batch-size 50`
2. Verify `batch_state.json` contains `"batch_size": 50`
3. Retry without `--batch-size`
4. Verify retry uses saved `batch_size=50`

## Priority

**Medium** - Affects users who use custom batch-size

## Acceptance Criteria

- [ ] `batch_state.json` includes `batch_size` field
- [ ] Retry without `--batch-size` uses saved value
- [ ] Explicit `--batch-size` overrides saved value
- [ ] Backward compatible with existing state files (defaults to 100)
