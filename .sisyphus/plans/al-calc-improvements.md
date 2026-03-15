# Al_calc 项目问题修复计划

## TL;DR

> **Quick Summary**: 修复远程 Al_calc 项目中发现的问题：HDF5 文件损坏、重复错误记录、进度文件并发写入冲突。采用 TDD 方法，确保代码质量和测试覆盖。
> 
> **Deliverables**:
> - HDF5 创建重试 + 损坏清理机制
> - 错误记录去重功能
> - 进度文件加锁保护
> - 错误类型细化
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES - 2 waves
> **Critical Path**: Task 1 → Task 3 → Task 5

---

## Context

### Original Request
分析远程 Al_calc 项目 (`/thfs4/home/xuyong/zeng/04.cluster/Al_calc`) 各阶段的问题，并与本地 deeplazy 代码对比，找出需要改进的地方。

### Interview Summary

**问题分析结果**:

| 问题 | 严重程度 | 根因 | 影响 |
|------|---------|------|------|
| HDF5 文件损坏 | P0 | NFS 并发写入冲突 + h5py 创建失败 | ~30% OLP 失败 |
| 重复错误记录 | P0 | `execute_batch` + `_collect_failed_tasks` 双重写入 | error_tasks 膨胀 |
| progress 并发写入 | P1 | 无文件锁保护 | 进度追踪混乱 |
| 错误类型识别粗略 | P1 | 统一处理不区分 HDF5 损坏/超时/节点错误 | 恢复策略不精准 |

**重复错误记录问题详解**:

用户准确指出：SLURM 数组任务分配正确，每个任务只被一个数组任务处理。问题是 **错误被两个独立的机制各记录一次**：

1. **即时记录**: `execute_batch` 捕获异常 → 调用 `record_error()` + `write_progress("error")`
2. **汇总记录**: `_collect_failed_tasks` 检测输出后 → 调用 `append_error_task()`

这导致同一个错误在 `error_tasks.jsonl` 和 `progress` 文件中各出现两次。

### Metis Review

**Identified Gaps** (addressed):
- **NFS 文件锁可靠性**: fcntl 在 NFS 上不可靠，需使用原子操作替代
- **任务边界计算**: 已确认 SLURM 数组任务分配正确，无重叠
- **错误分类**: 需要区分 HDF5_CORRUPTION、NETWORK_ERROR、PROCESS_TIMEOUT 等

---

## Work Objectives

### Core Objective
修复 Al_calc 项目发现的问题，提高批量计算工作流的稳定性和可靠性。

### Concrete Deliverables
- `dlazy/execution/olp_executor.py` - HDF5 重试机制
- `dlazy/core/tasks.py` - `append_error_task` 去重
- `dlazy/commands.py` - progress 文件加锁
- `dlazy/core/exceptions.py` - 错误类型细化
- `tests/` - 相关测试文件

### Definition of Done
- [ ] 所有测试通过: `pytest tests/`
- [ ] HDF5 损坏重试机制验证
- [ ] 错误记录无重复
- [ ] 进度文件写入有序

### Must Have
- HDF5 创建失败时自动重试 (最多 3 次)
- 错误记录去重 (按 path + task_id)
- progress 文件写入使用 FileLock

### Must NOT Have (Guardrails)
- 不修改 SLURM 脚本生成逻辑（已验证正确）
- 不改变任务分配边界计算
- 不删除现有功能

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (pytest)
- **Automated tests**: TDD (测试驱动开发)
- **Framework**: pytest
- **TDD workflow**: 每个任务遵循 RED (失败测试) → GREEN (最小实现) → REFACTOR

### QA Policy
每个任务包含 Agent-Executed QA Scenarios。Evidence 保存到 `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`。

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation):
├── Task 1: 错误类型细化 [quick]
├── Task 2: append_error_task 去重 [quick]
└── Task 3: progress 文件加锁 [quick]

Wave 2 (After Wave 1 — core improvements):
├── Task 4: HDF5 重试机制 [deep]
└── Task 5: 集成测试 [deep]
```

### Dependency Matrix

- **1, 2, 3**: — — 4, 5
- **4**: 1, 2, 3 — 5
- **5**: 1, 2, 3, 4 — —

### Agent Dispatch Summary

- **Wave 1**: 3 tasks → `quick`
- **Wave 2**: 2 tasks → `deep`

---

## TODOs

- [ ] 1. 错误类型细化 (FailureType 扩展)

  **What to do**:
  - 在 `dlazy/core/exceptions.py` 中扩展 `FailureType` 枚举
  - 添加 `HDF5_CORRUPTION`、`NETWORK_ERROR`、`EXTRACT_ERROR` 类型
  - 更新 `classify_error` 函数识别新类型

  **Must NOT do**:
  - 不要修改现有 `FailureType` 枚举值
  - 不要删除现有错误分类逻辑

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3)

  **References**:
  - `dlazy/core/exceptions.py` - 现有 FailureType 定义
  - `dlazy/core/workflow_state.py:FailureType` - 枚举定义位置

  **Acceptance Criteria**:
  - [ ] 测试文件创建: `tests/test_failure_types.py`
  - [ ] `pytest tests/test_failure_types.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: 新错误类型可正确分类
    Tool: Bash
    Steps:
      1. 运行 `pytest tests/test_failure_types.py -v`
      2. 验证 HDF5_CORRUPTION 类型的 classify_error 返回正确
    Expected Result: 所有测试通过
    Evidence: .sisyphus/evidence/task-01-test-pass.txt
  ```

- [ ] 2. append_error_task 去重

  **What to do**:
  - 在 `dlazy/core/tasks.py` 的 `append_error_task` 函数中添加去重检查
  - 检查文件中是否已存在相同 (path, task_id) 的记录
  - 使用 FileLock 保护读取和写入操作

  **Must NOT do**:
  - 不要改变现有错误记录格式
  - 不要删除已有错误记录

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3)

  **References**:
  - `dlazy/core/tasks.py` - append_error_task 函数位置
  - `dlazy/utils/concurrency.py:FileLock` - 文件锁实现

  **Acceptance Criteria**:
  - [ ] 测试文件创建: `tests/test_error_dedup.py`
  - [ ] `pytest tests/test_error_dedup.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: 重复错误记录被过滤
    Tool: Bash
    Steps:
      1. 创建临时 error_tasks.jsonl 文件
      2. 写入一条错误记录
      3. 再次写入相同的错误记录
      4. 验证文件中只有一条记录
    Expected Result: 文件中只有一条记录
    Evidence: .sisyphus/evidence/task-02-dedup.txt
  ```

- [ ] 3. progress 文件加锁

  **What to do**:
  - 在 `dlazy/commands.py` 的 `write_progress` 函数中添加 FileLock 保护
  - 使用 `dlazy/utils/concurrency.py:FileLock` 包装文件操作

  **Must NOT do**:
  - 不要改变 progress 文件格式
  - 不要删除现有进度记录

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)

  **References**:
  - `dlazy/commands.py:write_progress` - 函数位置 (第 252-254 行)
  - `dlazy/utils/concurrency.py:FileLock` - 文件锁实现

  **Acceptance Criteria**:
  - [ ] 测试文件创建: `tests/test_progress_lock.py`
  - [ ] `pytest tests/test_progress_lock.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: 并发写入 progress 文件有序
    Tool: Bash
    Steps:
      1. 创建多个进程同时写入 progress 文件
      2. 验证所有写入都成功
      3. 验证写入顺序正确
    Expected Result: 所有写入成功，无数据丢失
    Evidence: .sisyphus/evidence/task-03-progress-lock.txt
  ```

- [ ] 4. HDF5 重试机制

  **What to do**:
  - 在 `dlazy/execution/olp_executor.py` 中添加 HDF5 创建重试机制
  - 检测损坏的 HDF5 文件并清理
  - 使用 `HDF5IntegrityValidator` 验证输出
  - 最多重试 3 次，每次间隔 1 秒

  **Must NOT do**:
  - 不要改变 OLP 执行的主流程
  - 不要删除现有的验证逻辑

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocked By**: Tasks 1, 2, 3

  **References**:
  - `dlazy/execution/olp_executor.py` - OLP 执行器
  - `dlazy/core/validator/hdf5_integrity.py:HDF5IntegrityValidator` - HDF5 验证器

  **Acceptance Criteria**:
  - [ ] 测试文件创建: `tests/test_hdf5_retry.py`
  - [ ] `pytest tests/test_hdf5_retry.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: HDF5 创建失败时自动重试
    Tool: Bash
    Steps:
      1. 模拟 HDF5 创建失败场景
      2. 验证重试机制触发
      3. 验证最终成功或达到最大重试次数
    Expected Result: 重试机制正常工作
    Evidence: .sisyphus/evidence/task-04-hdf5-retry.txt

  Scenario: 损坏的 HDF5 文件被清理
    Tool: Bash
    Steps:
      1. 创建损坏的 HDF5 文件
      2. 运行 OLP 执行器
      3. 验证损坏文件被删除
    Expected Result: 损坏文件被清理，新文件创建成功
    Evidence: .sisyphus/evidence/task-04-hdf5-cleanup.txt
  ```

- [ ] 5. 集成测试

  **What to do**:
  - 创建集成测试验证所有改进协同工作
  - 测试完整 OLP 执行流程
  - 验证错误处理和恢复机制

  **Must NOT do**:
  - 不要跳过任何测试场景

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocked By**: Tasks 1, 2, 3, 4

  **References**:
  - `tests/` - 现有测试文件

  **Acceptance Criteria**:
  - [ ] 测试文件创建: `tests/test_integration_olp.py`
  - [ ] `pytest tests/` → ALL PASS

  **QA Scenarios**:
  ```
  Scenario: 完整 OLP 流程测试
    Tool: Bash
    Steps:
      1. 运行 `pytest tests/ -v --cov=dlazy`
      2. 验证所有测试通过
      3. 验证覆盖率报告
    Expected Result: 所有测试通过，覆盖率 > 80%
    Evidence: .sisyphus/evidence/task-05-integration.txt
  ```

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  验证所有 "Must Have" 已实现，所有 "Must NOT Have" 未触及。

- [ ] F2. **Code Quality Review** — `unspecified-high`
  运行 `pytest` + `ruff check`，确保代码质量。

- [ ] F3. **Integration Test** — `unspecified-high`
  运行完整测试套件，验证所有改进协同工作。

- [ ] F4. **Scope Fidelity Check** — `deep`
  验证所有修改符合计划范围，无范围蔓延。

---

## Commit Strategy

- **Task 1-3**: `fix(core): add error type classification and dedup` — 多文件
- **Task 4**: `fix(olp): add HDF5 retry mechanism` — olp_executor.py
- **Task 5**: `test: add integration tests for OLP improvements` — tests/

---

## Success Criteria

### Verification Commands
```bash
pytest tests/ -v --cov=dlazy  # Expected: all pass, coverage > 80%
ruff check dlazy/             # Expected: no errors
```

### Final Checklist
- [ ] 所有 "Must Have" 已实现
- [ ] 所有 "Must NOT Have" 未触及
- [ ] 所有测试通过
- [ ] HDF5 重试机制正常工作
- [ ] 错误记录无重复
