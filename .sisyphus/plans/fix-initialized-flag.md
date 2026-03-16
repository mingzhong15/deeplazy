# Fix: Set initialized=True in Lazy Creation Mode

## Problem

`batch-status` shows "状态: 未初始化" even when workflow is running.

**Root cause**: The lazy creation refactoring removed `initialized = True` setting.

```python
# cli.py line 454-456
if not initialized:
    print("状态: 未初始化")
    return
```

## Fix

**File**: `dlazy/batch_workflow.py`

**Location**: `run()` method, around line 770-778

**Change**:
```python
# Before
resolver = self._get_path_resolver(0)
todo_file = resolver.get_todo_list_file()
if todo_file.exists():
    tasks = list(_read_jsonl(todo_file))
    self.state["total_tasks"] = len(tasks)
    self.state["estimated_batches"] = math.ceil(
        len(tasks) / self.ctx.batch_size
    )
    self._save_state()  # Only saves if todo_file exists

# After
resolver = self._get_path_resolver(0)
todo_file = resolver.get_todo_list_file()
if todo_file.exists():
    tasks = list(_read_jsonl(todo_file))
    self.state["total_tasks"] = len(tasks)
    self.state["estimated_batches"] = math.ceil(
        len(tasks) / self.ctx.batch_size
    )
self.state["initialized"] = True  # Always set initialized
self._save_state()  # Always save state
```

## Acceptance Criteria

- [ ] `batch-status` shows current batch and stage when workflow running
- [ ] `initialized` field set to True on workflow start
