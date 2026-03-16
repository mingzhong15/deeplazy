# Enhancement: Lazy Batch Creation

## Problem

Current behavior creates ALL batch directories upfront:
- 704 tasks with batch_size=100 → creates batch.00000 ~ batch.00007 immediately
- If computation fails early, leaves empty directories
- Wastes disk space and creates confusion

## Proposed Solution: Create Batches On-Demand

### Current Flow
```
run() -> _init_batch_tasks() -> Creates ALL batches
      -> Loop through batches
```

### New Flow  
```
run() -> Loop:
      -> Check if batch.N needs to be created
      -> Create batch.N if not exists
      -> Process batch.N
      -> Move to batch.N+1
```

## Implementation

### Task 1: Modify `_init_batch_tasks()` to create single batch

**File**: `dlazy/batch_workflow.py`

**Add new method**:
```python
def _init_single_batch(self, batch_index: int) -> int:
    """Initialize a single batch's task file.
    
    Args:
        batch_index: Index of batch to create
        
    Returns:
        Number of tasks in this batch
    """
    resolver = self._get_path_resolver(0)
    todo_file = resolver.get_todo_list_file()
    
    if not todo_file.exists():
        return 0
    
    tasks = list(_read_jsonl(todo_file))
    if not tasks:
        return 0
    
    batch_size = self.ctx.batch_size
    start = batch_index * batch_size
    
    if start >= len(tasks):
        return 0  # No more tasks
    
    end = min(start + batch_size, len(tasks))
    batch_tasks = tasks[start:end]
    
    batch_resolver = self._get_path_resolver(batch_index)
    tasks_file = batch_resolver.get_olp_tasks_file()
    tasks_file.parent.mkdir(parents=True, exist_ok=True)
    
    olp_tasks = [OlpTask(path=t["path"]) for t in batch_tasks]
    write_olp_tasks(tasks_file, olp_tasks)
    
    self.logger.info("Created batch %d with %d tasks", batch_index, len(batch_tasks))
    return len(batch_tasks)
```

### Task 2: Modify main loop for lazy creation

**File**: `dlazy/batch_workflow.py`

**Change `run()` method** (around line 720):
```python
# Before
if not self.state.get("initialized"):
    start_batch = self.state.get("start_batch_index", 0)
    num_batches = self._init_batch_tasks(start_batch_index=start_batch)
    self.state["initialized"] = True
    self.state["total_batches"] = num_batches + start_batch
    self._save_state()

while self._has_pending_batches():
    ...
    
# After
# Calculate total tasks for progress tracking
resolver = self._get_path_resolver(0)
todo_file = resolver.get_todo_list_file()
if todo_file.exists():
    total_tasks = sum(1 for _ in _read_jsonl(todo_file))
    self.state["total_tasks"] = total_tasks
    self.state["estimated_batches"] = math.ceil(total_tasks / self.ctx.batch_size)
    self._save_state()

while True:
    batch_index = self.state["current_batch"]
    
    # Lazy create batch if not exists
    tasks_file = self._get_path_resolver(batch_index).get_olp_tasks_file()
    if not tasks_file.exists():
        num_tasks = self._init_single_batch(batch_index)
        if num_tasks == 0:
            break  # No more tasks, workflow complete
    else:
        num_tasks = self._count_batch_tasks(self._get_path_resolver(batch_index))
        if num_tasks == 0:
            break
    
    # Process batch...
    ...
```

### Task 3: Remove upfront batch creation

**Remove or deprecate `_init_batch_tasks()`** method that creates all batches at once.

### Task 4: Update `_has_pending_batches()`

```python
def _has_pending_batches(self) -> bool:
    """Check if there are more tasks to process."""
    resolver = self._get_path_resolver(0)
    todo_file = resolver.get_todo_list_file()
    
    if not todo_file.exists():
        return False
    
    total_tasks = sum(1 for _ in _read_jsonl(todo_file))
    processed_tasks = self.state["current_batch"] * self.ctx.batch_size
    
    return processed_tasks < total_tasks
```

## Benefits

| Before | After |
|--------|-------|
| Creates all batch dirs upfront | Creates one batch at a time |
| Empty dirs if early failure | No wasted directories |
| `total_batches` known upfront | `estimated_batches` (may grow with retries) |
| Confusing `append` mode | Clear: always continue from `current_batch` |

## New Behavior

```bash
# First run: 704 tasks, batch_size=100
dlazy batch --config global_config.yaml
# Creates batch.00000 with 100 tasks
# Processes batch.00000...
# Creates batch.00001 with 100 tasks
# Processes batch.00001...
# Ctrl+C interrupts

# Resume:
dlazy batch --config global_config.yaml
# Reads state: current_batch=2
# Creates batch.00002 with 100 tasks (lazy!)
# Processes batch.00002...
```

## Acceptance Criteria

- [ ] Batches created on-demand, not upfront
- [ ] Resume works correctly from any batch
- [ ] No empty batch directories left on failure
- [ ] Progress tracking still works
- [ ] Retry mechanism (failed task relay) still works
