# Fix: Remove Interactive Prompt for Batch Mode

## Problem

**Current behavior causes nohup failure**:

```
检测到已有批次: batch.00000 ~ batch.00003
请选择处理方式:
  [1] append    - 从 batch.00004 继续添加新批次
  [2] overwrite - 删除所有批次，从 batch.00000 重新开始
请输入选择 (1/2): Traceback ...
OSError: [Errno 9] Bad file descriptor
```

**Root cause**: `input()` fails when running with nohup (no terminal).

## Proposed Solution

**Make `auto` mode non-interactive**: Auto-select `append` when existing batches detected.

### Task 1: Modify CLI batch mode handling

**File**: `dlazy/cli.py`

**Location**: `cmd_batch()` function, lines 203-222

**Change**:
```python
# Before (interactive, fails in nohup)
if existing_count > 0 and batch_mode == "auto":
    print(f"\n检测到已有批次: batch.00000 ~ batch.{existing_count - 1:05d}")
    print("请选择处理方式:")
    print("  [1] append    - 从 batch.{:05d} 继续添加新批次".format(existing_count))
    print("  [2] overwrite - 删除所有批次，从 batch.00000 重新开始")

    while True:
        choice = input("请输入选择 (1/2): ").strip()
        if choice == "1":
            batch_mode = "append"
            break
        elif choice == "2":
            batch_mode = "overwrite"
            break
        else:
            print("无效输入，请输入 1 或 2")

# After (non-interactive, works in nohup)
if batch_mode == "auto":
    batch_mode = "append"
    if existing_count > 0:
        print(f"检测到已有批次: batch.00000 ~ batch.{existing_count - 1:05d}")
        print(f"自动选择: append - 从 batch.{existing_count:05d} 继续")
```

### Task 2: Update help text

**File**: `dlazy/cli.py`

**Location**: Line 924

**Change**:
```python
# Before
help="批次处理模式: auto(检测到已有批次时提示), append(追加), overwrite(覆盖)",

# After
help="批次处理模式: auto(自动追加), append(追加), overwrite(覆盖删除)",
```

## New Behavior

| Command | Existing Batches | Behavior |
|---------|------------------|----------|
| `dlazy batch` | None | Start fresh |
| `dlazy batch` | Yes | Auto append (no prompt) |
| `dlazy batch --batch-mode append` | Yes | Append |
| `dlazy batch --batch-mode overwrite` | Yes | Delete all, restart |
| `dlazy batch --fresh` | Yes | Delete state, continue from existing batches |

## Benefits

1. **Works with nohup**: No interactive prompt
2. **Safer default**: Never accidentally delete data
3. **Simpler**: Less code, clearer behavior
4. **Backward compatible**: Same CLI arguments

## Acceptance Criteria

- [ ] `dlazy batch` with existing batches auto-appends without prompt
- [ ] Works correctly with `nohup` and background execution
- [ ] `--batch-mode overwrite` still works to force restart
- [ ] Help text updated
