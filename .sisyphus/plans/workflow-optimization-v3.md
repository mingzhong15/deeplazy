# Workflow Optimization V3 - 全面优化升级计划

## TL;DR

> **Quick Summary**: 全面重构deeplazy的调度、错误分析和断点续传系统，参考dpgen最佳实践，引入验证模块和多级恢复策略。
> 
> **Deliverables**:
> - 新调度模块 `scheduler/` (SLURM专用，任务分组，资源监控)
> - 验证模块 `validator/` (SCF收敛检查 + HDF5完整性)
> - 恢复模块 `recovery/` (多级恢复策略 + xxh64校验)
> - 状态模块 `state/` (任务级状态追踪)
> - 重构执行器 `executor/` (模块化设计)
> - 全新CLI (Rich进度条)
> 
> **Estimated Effort**: XL (Large refactoring)
> **Parallel Execution**: YES - 5 waves
> **Critical Path**: Tests → Validator → State → Scheduler → Integration

---

## Context

### Original Request
参考 ~/zeng/github/dpgen 项目的调度、错误分析、断点续传实现，对 deeplazy 项目进行全面优化升级。

### Interview Summary
**Key Discussions**:
- 对比分析了两个项目的架构差异
- dpgen使用dpdispatcher抽象层，支持多调度器和任务分组
- deeplazy优势：统一异常体系、任务中继系统、Monitor模式
- 用户选择全面优化，但保持SLURM only

**User Decisions**:
| 决策项 | 选择 |
|--------|------|
| 优化方向 | 全面优化（调度+错误分析+断点续传） |
| 调度器 | SLURM only |
| 错误分析 | 物理计算验证 |
| SCF检查 | 迭代次数限制 |
| HDF5验证 | 结构+数据集+NaN/Inf |
| 断点续传 | 任务级状态+多级恢复+数据校验 |
| 兼容性 | 全新设计 |
| 数据迁移 | 不迁移，全新开始 |
| 实现方式 | 单次全面重构 |
| 测试策略 | TDD开发 |
| 数据校验 | xxh64 |
| 状态存储 | JSON文件 |
| 进度可视化 | Rich进度条 |
| 并发策略 | multiprocessing.Pool |
| SLURM测试 | 真实集群测试 |

### Metis Review
**Identified Gaps** (resolved):
- 数据迁移：不迁移
- Import兼容：不需要
- xxHash变体：xxh64
- SCF收敛：迭代次数检查
- SLURM测试：真实集群

---

## Work Objectives

### Core Objective
重构deeplazy项目架构，实现模块化的调度系统、智能化的错误分析和可靠的断点续传机制，同时保持SLURM专用和全新设计原则。

### Concrete Deliverables
- `dlazy/scheduler/` - 调度模块（SLURM专用）
- `dlazy/core/validator/` - 验证模块（SCF + HDF5）
- `dlazy/core/recovery/` - 恢复模块（多级策略）
- `dlazy/state/` - 状态模块（任务级追踪）
- `dlazy/executor/` - 重构执行器
- `dlazy/cli.py` - 全新CLI（Rich进度条）
- 完整测试覆盖（pytest）

### Definition of Done
- [ ] 所有模块有对应测试文件
- [ ] pytest tests/ 通过（覆盖率 > 80%）
- [ ] 在真实SLURM集群上验证完整工作流
- [ ] 所有验收标准有对应测试用例

### Must Have
- SLURM调度器支持（任务提交、状态轮询、资源监控）
- SCF收敛性检查（OpenMX输出解析）
- HDF5完整性验证（文件结构、数据集、NaN/Inf）
- 任务级状态追踪（pending/running/success/failed/temp_fail/perm_fail）
- 多级恢复策略（临时失败/永久失败/配置错误）
- 数据完整性校验（xxh64）
- Rich进度条可视化

### Must NOT Have (Guardrails)
- 不添加PBS/LSF/Local调度器支持
- 不创建Web UI或Dashboard
- 不实现数据迁移工具
- 不添加向后兼容层
- 不引入新的日志框架
- 不修改配置文件格式
- 不添加外部数据库依赖

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (pytest in pyproject.toml)
- **Automated tests**: TDD (tests written BEFORE implementation)
- **Framework**: pytest
- **Each task follows**: RED (failing test) → GREEN (minimal impl) → REFACTOR

### QA Policy
Every task MUST include agent-executed QA scenarios.

- **Library/Module**: Use pytest - Import, call functions, assert outputs
- **SLURM Integration**: Test on real cluster `/thfs4/home/xuyong/zeng/04.cluster/Ag_calc`
- **CLI**: Use subprocess - Run commands, check exit code + output
- **End-to-end**: Full workflow on test data

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - Tests + Infrastructure):
├── Task 1: Test infrastructure setup [quick]
├── Task 2: Test fixtures (HDF5 samples, OpenMX outputs) [quick]
├── Task 3: Base classes + interfaces [quick]
├── Task 4: xxh64 checksum utility [quick]
└── Task 5: Rich progress integration [quick]

Wave 2 (Core Modules - MAX PARALLEL):
├── Task 6: Validator base + registry [quick]
├── Task 7: SCF convergence validator [deep]
├── Task 8: HDF5 integrity validator [deep]
├── Task 9: Recovery base + strategies [deep]
├── Task 10: State module (task_state.py) [deep]
├── Task 11: Checkpoint manager [deep]
└── Task 12: State serializer [quick]

Wave 3 (Scheduler + Executor):
├── Task 13: Scheduler base + interfaces [quick]
├── Task 14: SLURM scheduler [deep]
├── Task 15: Job manager [deep]
├── Task 16: Resource monitor [quick]
├── Task 17: Executor base [quick]
├── Task 18: OLP executor [deep]
├── Task 19: Infer executor [deep]
└── Task 20: Calc executor [deep]

Wave 4 (Integration + CLI):
├── Task 21: Batch scheduler refactor [deep]
├── Task 22: CLI refactor with Rich [visual-engineering]
├── Task 23: Integration tests [deep]
└── Task 24: SLURM cluster validation [deep]

Wave FINAL (Verification):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real cluster E2E test (unspecified-high)
└── Task F4: Scope fidelity check (deep)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|------------|--------|
| 1-5 | — | 6-12 |
| 6 | 1, 3 | 7, 8 |
| 7, 8 | 2, 6 | 18, 19, 20 |
| 9 | 1, 3, 4 | 21 |
| 10, 11, 12 | 1, 3 | 21 |
| 13 | 1, 3 | 14, 15, 16 |
| 14, 15, 16 | 10, 13 | 21 |
| 17 | 1, 3 | 18, 19, 20 |
| 18, 19, 20 | 7, 8, 17 | 23 |
| 21 | 9, 10, 11, 14, 15 | 23, 24 |
| 22 | 5, 21 | 24 |
| 23 | 18, 19, 20, 21 | F3 |
| 24 | 22, 23 | F3 |
| F1-F4 | ALL | — |

---

## TODOs

> Implementation + Test = ONE Task.
> EVERY task MUST have: Recommended Agent Profile + Parallelization + QA Scenarios.

### Wave 1: Foundation (Tests + Infrastructure) ✅ COMPLETED

- [x] 1. **Test Infrastructure Setup** ✅

  **What to do**:
  - Create `tests/conftest.py` with shared fixtures
  - Create `tests/fixtures/` directory structure
  - Add pytest configuration for markers (slurm, slow, integration)
  - Add coverage configuration in `pyproject.toml`

  **Must NOT do**:
  - Don't modify existing test files yet
  - Don't add new test dependencies beyond pytest-cov

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [] (basic setup)

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2-5)
  - **Blocks**: Tasks 6-12

  **References**:
  - `pyproject.toml:tool.pytest` - Current pytest config
  - `tests/` - Existing test structure

  **Acceptance Criteria**:
  - [ ] `tests/conftest.py` exists with basic fixtures
  - [ ] `tests/fixtures/` directory created
  - [ ] `pytest tests/ -v` runs without error
  - [ ] `pytest --cov=dlazy` reports coverage

  **QA Scenarios**:
  ```
  Scenario: Run pytest with new config
    Tool: Bash
    Steps:
      1. pytest tests/ -v --collect-only
      2. Assert: collected N tests (N > 0)
    Expected: Tests collected successfully
    Evidence: .sisyphus/evidence/task-01-pytest-collect.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `test: add test infrastructure setup`
  - Files: `tests/conftest.py`, `tests/fixtures/.gitkeep`, `pyproject.toml`

- [x] 2. **Test Fixtures (HDF5 Samples, OpenMX Outputs)** ✅

  **What to do**:
  - Create sample HDF5 files in `tests/fixtures/`
    - `valid_overlaps.h5` - Valid overlaps file
    - `valid_hamiltonians.h5` - Valid Hamiltonians file
    - `corrupted.h5` - Corrupted HDF5 for error testing
    - `empty.h5` - Empty HDF5 file
    - `nan_values.h5` - HDF5 with NaN/Inf values
  - Create sample OpenMX output files
    - `scf_converged.out` - Converged SCF output
    - `scf_not_converged.out` - Non-converged SCF output
  - Add fixtures in `conftest.py` to load these files

  **Must NOT do**:
  - Don't create large files (>1MB each)
  - Don't use real proprietary data

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3-5)
  - **Blocks**: Tasks 7, 8 (validators)

  **References**:
  - `dlazy/constants.py` - HDF5 filename constants
  - Existing HDF5 files in workflow for structure reference

  **Acceptance Criteria**:
  - [ ] All 6 HDF5 fixtures exist and are valid HDF5 files
  - [ ] All 2 OpenMX fixtures exist with expected content
  - [ ] `conftest.py` has fixtures to load each file

  **QA Scenarios**:
  ```
  Scenario: Load valid HDF5 fixture
    Tool: Bash (python)
    Steps:
      1. python -c "import h5py; f = h5py.File('tests/fixtures/valid_overlaps.h5'); print(list(f.keys()))"
    Expected: Keys printed without error
    Evidence: .sisyphus/evidence/task-02-hdf5-load.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `test: add HDF5 and OpenMX test fixtures`
  - Files: `tests/fixtures/*.h5`, `tests/fixtures/*.out`, `tests/conftest.py`

- [x] 3. **Base Classes + Interfaces** ✅

  **What to do**:
  - Create `dlazy/core/validator/base.py`:
    - `Validator` abstract base class with `validate(path) -> ValidationResult`
    - `ValidationResult` dataclass with `is_valid`, `errors`, `warnings`
  - Create `dlazy/core/recovery/base.py`:
    - `RecoveryStrategy` abstract base class with `can_recover(error) -> bool`, `recover(context) -> RecoveryAction`
    - `RecoveryAction` enum: RETRY, SKIP, ABORT
  - Create `dlazy/scheduler/base.py`:
    - `Scheduler` abstract base class with `submit()`, `check_status()`, `cancel()`
    - `JobInfo` dataclass with `job_id`, `status`, `submit_time`
  - Create `dlazy/executor/base.py`:
    - `Executor` abstract base class with `execute(task) -> TaskResult`
    - `TaskResult` dataclass with `status`, `output_path`, `errors`
  - Write TDD tests for all base classes

  **Must NOT do**:
  - Don't add implementation details to base classes
  - Don't create generic scheduler abstraction (SLURM only design)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4, 5)
  - **Blocks**: Tasks 6, 9, 13, 17

  **References**:
  - `dlazy/core/exceptions.py` - Existing exception hierarchy
  - `dlazy/core/tasks.py` - Existing dataclass patterns

  **Acceptance Criteria**:
  - [ ] All 4 base modules exist with abstract base classes
  - [ ] All tests in `tests/test_base_classes.py` pass
  - [ ] `pytest tests/test_base_classes.py -v` shows 100% pass

  **QA Scenarios**:
  ```
  Scenario: Instantiate abstract class fails
    Tool: Bash (python)
    Steps:
      1. python -c "from dlazy.core.validator.base import Validator; v = Validator()"
    Expected: TypeError: Can't instantiate abstract class
    Evidence: .sisyphus/evidence/task-03-abstract.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat: add base classes for validator, recovery, scheduler, executor`
  - Files: `dlazy/core/validator/base.py`, `dlazy/core/recovery/base.py`, `dlazy/scheduler/base.py`, `dlazy/executor/base.py`, `tests/test_base_classes.py`

- [x] 4. **xxh64 Checksum Utility** ✅

  **What to do**:
  - Add `xxhash` to dependencies in `pyproject.toml`
  - Create `dlazy/core/recovery/checksum.py`:
    - `compute_checksum(file_path: Path, algorithm: str = "xxh64") -> str`
    - `verify_checksum(file_path: Path, expected: str) -> bool`
    - `compute_checksum_streaming(file_path: Path, chunk_size: int = 8192) -> str` for large files
  - Write TDD tests with fixtures from Task 2

  **Must NOT do**:
  - Don't use MD5 or SHA256 (use xxh64 only)
  - Don't add unnecessary options

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-3, 5)
  - **Blocks**: Task 11 (checkpoint manager)

  **References**:
  - `tests/fixtures/valid_overlaps.h5` - Test file for checksum
  - xxhash library docs: `https://github.com/ifduyue/python-xxhash`

  **Acceptance Criteria**:
  - [ ] `xxhash` in `pyproject.toml` dependencies
  - [ ] `compute_checksum()` works on test fixtures
  - [ ] `verify_checksum()` returns correct boolean
  - [ ] All tests in `tests/test_checksum.py` pass

  **QA Scenarios**:
  ```
  Scenario: Compute and verify checksum
    Tool: Bash (python)
    Steps:
      1. python -c "from dlazy.core.recovery.checksum import compute_checksum, verify_checksum; h = compute_checksum('tests/fixtures/valid_overlaps.h5'); print(h); print(verify_checksum('tests/fixtures/valid_overlaps.h5', h))"
    Expected: Hash string printed, True returned
    Evidence: .sisyphus/evidence/task-04-checksum.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat: add xxh64 checksum utility`
  - Files: `dlazy/core/recovery/checksum.py`, `tests/test_checksum.py`, `pyproject.toml`

- [x] 5. **Rich Progress Integration** ✅

  **What to do**:
  - Add `rich` to dependencies in `pyproject.toml`
  - Create `dlazy/utils/progress.py`:
    - `create_progress_bar()` - Factory for Rich Progress
    - `TaskProgress` class with `start()`, `update()`, `complete()` methods
    - `BatchProgress` class for tracking batch-level progress
  - Design for multiprocessing compatibility (main process displays progress)
  - Write TDD tests (mock Rich for unit tests)

  **Must NOT do**:
  - Don't add Web UI or dashboard
  - Don't use Rich in worker processes (only main process)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [] (utility module)

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-4)
  - **Blocks**: Task 22 (CLI refactor)

  **References**:
  - Rich library docs: `https://rich.readthedocs.io/`
  - `dlazy/batch_workflow.py` - Current status display for context

  **Acceptance Criteria**:
  - [ ] `rich` in `pyproject.toml` dependencies
  - [ ] `TaskProgress` class works with mock Rich
  - [ ] `BatchProgress` tracks multiple tasks
  - [ ] All tests in `tests/test_progress.py` pass

  **QA Scenarios**:
  ```
  Scenario: Progress bar creation and update
    Tool: Bash (python)
    Steps:
      1. python -c "from dlazy.utils.progress import TaskProgress; p = TaskProgress(total=100); p.update(50); print(p.completed)"
    Expected: 50 printed
    Evidence: .sisyphus/evidence/task-05-progress.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat: add Rich progress utility`
  - Files: `dlazy/utils/progress.py`, `tests/test_progress.py`, `pyproject.toml`

---

### Wave 2: Core Modules (Validator + Recovery + State) ✅ COMPLETED

- [x] 6. **Validator Base + Registry** ✅

  **What to do**:
  - Create `dlazy/core/validator/__init__.py` with exports
  - Create `dlazy/core/validator/registry.py`:
    - `ValidatorRegistry` class with `register()`, `get()`, `get_all()` methods
    - Decorator `@register_validator(name)` for auto-registration
    - `get_validators_for_stage(stage: str) -> List[Validator]`
  - Update `base.py` with `validator_type` attribute
  - Write TDD tests with mock validators

  **Must NOT do**:
  - Don't add plugin loading from external files
  - Don't add more than 2 validator types (SCF, HDF5)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-12)
  - **Blocks**: Tasks 7, 8 (depend on registry)

  **References**:
  - `dlazy/core/validator/base.py` - Base class from Task 3
  - `dlazy/core/exceptions.py:FailureType` - For validation errors

  **Acceptance Criteria**:
  - [ ] `ValidatorRegistry` can register and retrieve validators
  - [ ] `@register_validator()` decorator works
  - [ ] All tests in `tests/test_validator_registry.py` pass

  **QA Scenarios**:
  ```
  Scenario: Register and retrieve validator
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.core.validator.base import Validator
from dlazy.core.validator.registry import ValidatorRegistry, register_validator

@register_validator('test')
class TestValidator(Validator):
    def validate(self, path):
        from dlazy.core.validator.base import ValidationResult
        return ValidationResult(is_valid=True)

r = ValidatorRegistry()
print('test' in [v.validator_type for v in r.get_all()])
"
    Expected: True
    Evidence: .sisyphus/evidence/task-06-registry.txt
  ```

  **Commit**: YES (groups with Wave 2 validators)
  - Message: `feat(validator): add validator registry`
  - Files: `dlazy/core/validator/__init__.py`, `dlazy/core/validator/registry.py`, `tests/test_validator_registry.py`

- [x] 7. **SCF Convergence Validator** ✅

  **What to do**:
  - Create `dlazy/core/validator/scf_convergence.py`:
    - `SCFConvergenceValidator` class implementing `Validator`
    - `parse_scf_iterations(output_file: Path) -> int` - Parse SCF iteration count
    - `check_convergence(output_file: Path, max_iterations: int) -> ValidationResult`
    - Support OpenMX output format
  - Register with `@register_validator('scf_convergence')`
  - Write TDD tests using fixtures from Task 2

  **Must NOT do**:
  - Don't add energy threshold checking (iteration count only per user choice)
  - Don't support multiple DFT codes (OpenMX only)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 8-12)
  - **Blocks**: Tasks 18-20 (executors use validator)

  **References**:
  - `tests/fixtures/scf_converged.out` - Converged SCF output
  - `tests/fixtures/scf_not_converged.out` - Non-converged output
  - OpenMX output format documentation

  **Acceptance Criteria**:
  - [ ] `SCFConvergenceValidator` registered in registry
  - [ ] Correctly parses SCF iteration count from OpenMX output
  - [ ] Returns `is_valid=False` for non-converged outputs
  - [ ] All tests in `tests/test_scf_validator.py` pass

  **QA Scenarios**:
  ```
  Scenario: Validate converged SCF
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.core.validator.scf_convergence import SCFConvergenceValidator
v = SCFConvergenceValidator(max_iterations=100)
result = v.validate('tests/fixtures/scf_converged.out')
print(f'is_valid={result.is_valid}, iterations={result.details.get(\"iterations\")}')
"
    Expected: is_valid=True, iterations=<N>
    Evidence: .sisyphus/evidence/task-07-scf-valid.txt

  Scenario: Validate non-converged SCF
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.core.validator.scf_convergence import SCFConvergenceValidator
v = SCFConvergenceValidator(max_iterations=100)
result = v.validate('tests/fixtures/scf_not_converged.out')
print(f'is_valid={result.is_valid}, errors={result.errors}')
"
    Expected: is_valid=False, errors non-empty
    Evidence: .sisyphus/evidence/task-07-scf-invalid.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(validator): add SCF convergence validator`
  - Files: `dlazy/core/validator/scf_convergence.py`, `tests/test_scf_validator.py`

- [x] 8. **HDF5 Integrity Validator** ✅

  **What to do**:
  - Create `dlazy/core/validator/hdf5_integrity.py`:
    - `HDF5IntegrityValidator` class implementing `Validator`
    - `check_file_openable(path: Path) -> bool`
    - `check_required_datasets(path: Path, required: List[str]) -> List[str]` - Returns missing datasets
    - `check_nan_inf(path: Path) -> List[str]` - Returns datasets with NaN/Inf
    - `check_data_shapes(path: Path, expected_shapes: Dict[str, Tuple]) -> List[str]`
  - Register with `@register_validator('hdf5_integrity')`
  - Write TDD tests using fixtures from Task 2

  **Must NOT do**:
  - Don't add checksum validation (separate task)
  - Don't validate HDF5 metadata beyond datasets

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 9-12)
  - **Blocks**: Tasks 18-20 (executors use validator)

  **References**:
  - `tests/fixtures/valid_overlaps.h5` - Valid HDF5
  - `tests/fixtures/corrupted.h5` - Corrupted HDF5
  - `tests/fixtures/nan_values.h5` - HDF5 with NaN
  - `dlazy/constants.py:OVERLAP_FILENAME, HAMILTONIAN_FILENAME` - Expected datasets

  **Acceptance Criteria**:
  - [ ] `HDF5IntegrityValidator` registered in registry
  - [ ] Detects corrupted HDF5 files
  - [ ] Detects missing required datasets
  - [ ] Detects NaN/Inf values in datasets
  - [ ] All tests in `tests/test_hdf5_validator.py` pass

  **QA Scenarios**:
  ```
  Scenario: Validate valid HDF5
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.core.validator.hdf5_integrity import HDF5IntegrityValidator
v = HDF5IntegrityValidator(required_datasets=['overlaps'])
result = v.validate('tests/fixtures/valid_overlaps.h5')
print(f'is_valid={result.is_valid}')
"
    Expected: is_valid=True
    Evidence: .sisyphus/evidence/task-08-hdf5-valid.txt

  Scenario: Validate corrupted HDF5
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.core.validator.hdf5_integrity import HDF5IntegrityValidator
v = HDF5IntegrityValidator()
result = v.validate('tests/fixtures/corrupted.h5')
print(f'is_valid={result.is_valid}, errors={result.errors}')
"
    Expected: is_valid=False
    Evidence: .sisyphus/evidence/task-08-hdf5-corrupt.txt

  Scenario: Detect NaN values
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.core.validator.hdf5_integrity import HDF5IntegrityValidator
v = HDF5IntegrityValidator()
result = v.validate('tests/fixtures/nan_values.h5')
print(f'has_nan={\"NaN detected\" in str(result.errors)}')
"
    Expected: has_nan=True
    Evidence: .sisyphus/evidence/task-08-hdf5-nan.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(validator): add HDF5 integrity validator`
  - Files: `dlazy/core/validator/hdf5_integrity.py`, `tests/test_hdf5_validator.py`

- [x] 9. **Recovery Base + Strategies** ✅

  **What to do**:
  - Create `dlazy/core/recovery/__init__.py` with exports
  - Create `dlazy/core/recovery/strategies.py`:
    - `RetryStrategy` - Retry for transient errors (up to N times)
    - `SkipStrategy` - Skip task and continue (for permanent failures)
    - `AbortStrategy` - Abort entire workflow (for critical errors)
    - `RecoveryStrategyChain` - Chain multiple strategies
  - Map `FailureType` to appropriate strategy
  - Write TDD tests

  **Must NOT do**:
  - Don't add more than 3 recovery strategies
  - Don't add complex strategy patterns (keep it simple)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6-8, 10-12)
  - **Blocks**: Task 21 (batch scheduler uses recovery)

  **References**:
  - `dlazy/core/exceptions.py:FailureType` - Error types
  - `dlazy/core/recovery/base.py` - Base class from Task 3
  - `dlazy/constants.py:MAX_RETRY_COUNT` - Retry limit

  **Acceptance Criteria**:
  - [ ] All 3 strategies implement `RecoveryStrategy`
  - [ ] `RecoveryStrategyChain` executes strategies in order
  - [ ] FailureType to strategy mapping works
  - [ ] All tests in `tests/test_recovery_strategies.py` pass

  **QA Scenarios**:
  ```
  Scenario: Retry strategy recovers transient error
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.core.recovery.strategies import RetryStrategy
from dlazy.core.recovery.base import RecoveryAction
from dlazy.core.exceptions import FailureType
s = RetryStrategy(max_retries=3)
ctx = {'retry_count': 1, 'failure_type': FailureType.NODE_ERROR}
print(f'can_recover={s.can_recover(ctx)}, action={s.recover(ctx)}')
"
    Expected: can_recover=True, action=RETRY
    Evidence: .sisyphus/evidence/task-09-retry.txt

  Scenario: Skip strategy for permanent failure
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.core.recovery.strategies import SkipStrategy
from dlazy.core.recovery.base import RecoveryAction
from dlazy.core.exceptions import FailureType
s = SkipStrategy()
ctx = {'failure_type': FailureType.CONFIG_ERROR}
print(f'action={s.recover(ctx)}')
"
    Expected: action=SKIP
    Evidence: .sisyphus/evidence/task-09-skip.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(recovery): add recovery strategies`
  - Files: `dlazy/core/recovery/__init__.py`, `dlazy/core/recovery/strategies.py`, `tests/test_recovery_strategies.py`

- [x] 10. **State Module (task_state.py)** ✅

  **What to do**:
  - Create `dlazy/state/__init__.py` with exports
  - Create `dlazy/state/task_state.py`:
    - `TaskState` enum: PENDING, RUNNING, SUCCESS, FAILED, TEMP_FAIL, PERM_FAIL
    - `TaskStatus` dataclass: task_id, state, stage, start_time, end_time, error_message, retry_count, checksum
    - `TaskStateStore` class: in-memory store with JSON persistence
    - `transition(task_id, new_state)` method with validation
    - `get_by_state(state) -> List[TaskStatus]`
    - `get_by_stage(stage) -> List[TaskStatus]`
  - Write TDD tests

  **Must NOT do**:
  - Don't add database backend (JSON only)
  - Don't add more states than defined

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6-9, 11, 12)
  - **Blocks**: Task 14 (SLURM scheduler), Task 21 (batch scheduler)

  **References**:
  - `dlazy/core/tasks.py` - Existing task data structures
  - `dlazy/utils/concurrency.py:atomic_write_json` - JSON persistence
  - `dlazy/core/workflow_state.py:MonitorState` - Similar pattern

  **Acceptance Criteria**:
  - [ ] `TaskState` enum has all 6 states
  - [ ] `TaskStateStore` persists to JSON
  - [ ] State transitions are validated (no invalid transitions)
  - [ ] All tests in `tests/test_task_state.py` pass

  **QA Scenarios**:
  ```
  Scenario: State transitions
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.state.task_state import TaskState, TaskStatus, TaskStateStore
store = TaskStateStore()
store.add(TaskStatus(task_id='t1', state=TaskState.PENDING, stage='olp'))
store.transition('t1', TaskState.RUNNING)
print(store.get('t1').state)
"
    Expected: TaskState.RUNNING
    Evidence: .sisyphus/evidence/task-10-state.txt

  Scenario: Invalid transition rejected
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.state.task_state import TaskState, TaskStatus, TaskStateStore
store = TaskStateStore()
store.add(TaskStatus(task_id='t1', state=TaskState.SUCCESS, stage='olp'))
try:
    store.transition('t1', TaskState.RUNNING)
    print('allowed')
except ValueError as e:
    print(f'rejected: {e}')
"
    Expected: rejected: (transition from SUCCESS to RUNNING invalid)
    Evidence: .sisyphus/evidence/task-10-invalid.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(state): add task state module`
  - Files: `dlazy/state/__init__.py`, `dlazy/state/task_state.py`, `tests/test_task_state.py`

- [x] 11. **Checkpoint Manager** ✅

  **What to do**:
  - Create `dlazy/state/checkpoint.py`:
    - `Checkpoint` dataclass: task_id, stage, output_path, checksum, timestamp
    - `CheckpointManager` class:
      - `save_checkpoint(task_id, output_path)` - Compute and store checkpoint
      - `verify_checkpoint(task_id) -> bool` - Verify checksum matches
      - `load_checkpoint(task_id) -> Optional[Checkpoint]`
      - `list_checkpoints(stage: Optional[str]) -> List[Checkpoint]`
    - Integration with `checksum.py` from Task 4
  - Write TDD tests

  **Must NOT do**:
  - Don't store checkpoints in a separate database
  - Don't add incremental checkpointing

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6-10, 12)
  - **Blocks**: Task 21 (batch scheduler uses checkpoint)

  **References**:
  - `dlazy/core/recovery/checksum.py` - xxh64 functions
  - `dlazy/state/task_state.py` - Task state integration
  - `dlazy/utils/concurrency.py:atomic_write_json` - Persistence

  **Acceptance Criteria**:
  - [ ] `CheckpointManager` saves checkpoint with xxh64 hash
  - [ ] `verify_checkpoint()` detects file changes
  - [ ] Checkpoints persisted to JSON file
  - [ ] All tests in `tests/test_checkpoint.py` pass

  **QA Scenarios**:
  ```
  Scenario: Save and verify checkpoint
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.state.checkpoint import CheckpointManager
import tempfile
import os

with tempfile.TemporaryDirectory() as tmpdir:
    mgr = CheckpointManager(checkpoint_dir=tmpdir)
    # Create test file
    test_file = os.path.join(tmpdir, 'test.h5')
    with open(test_file, 'w') as f:
        f.write('test data')
    
    mgr.save_checkpoint('t1', test_file, stage='olp')
    result = mgr.verify_checkpoint('t1')
    print(f'verified={result}')
"
    Expected: verified=True
    Evidence: .sisyphus/evidence/task-11-checkpoint.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(state): add checkpoint manager`
  - Files: `dlazy/state/checkpoint.py`, `tests/test_checkpoint.py`

- [x] 12. **State Serializer** ✅

  **What to do**:
  - Create `dlazy/state/serializer.py`:
    - `StateSerializer` class:
      - `serialize(store: TaskStateStore) -> Dict` - Convert to JSON-safe dict
      - `deserialize(data: Dict) -> TaskStateStore` - Reconstruct from dict
      - `save_to_file(store, path: Path)` - Atomic save
      - `load_from_file(path: Path) -> TaskStateStore` - Load with validation
    - Handle `CheckpointManager` serialization
    - Handle version field for future compatibility
  - Write TDD tests

  **Must NOT do**:
  - Don't add pickle/yaml support (JSON only)
  - Don't add encryption

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6-11)
  - **Blocks**: Task 21 (batch scheduler uses serialization)

  **References**:
  - `dlazy/state/task_state.py` - TaskStateStore
  - `dlazy/state/checkpoint.py` - CheckpointManager
  - `dlazy/utils/concurrency.py:atomic_write_json` - Atomic write utility

  **Acceptance Criteria**:
  - [ ] `StateSerializer` round-trips TaskStateStore
  - [ ] Includes version field in serialized output
  - [ ] Atomic file write using existing utility
  - [ ] All tests in `tests/test_serializer.py` pass

  **QA Scenarios**:
  ```
  Scenario: Round-trip serialization
    Tool: Bash (python)
    Steps:
      1. python -c "
from dlazy.state.task_state import TaskState, TaskStatus, TaskStateStore
from dlazy.state.serializer import StateSerializer
import tempfile
import os

store = TaskStateStore()
store.add(TaskStatus(task_id='t1', state=TaskState.PENDING, stage='olp'))

with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, 'state.json')
    serializer = StateSerializer()
    serializer.save_to_file(store, path)
    loaded = serializer.load_from_file(path)
    print(f'match={loaded.get(\"t1\").task_id == \"t1\"}')
"
    Expected: match=True
    Evidence: .sisyphus/evidence/task-12-serializer.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(state): add state serializer`
  - Files: `dlazy/state/serializer.py`, `tests/test_serializer.py`

---

### Wave 3: Scheduler + Executor ✅ COMPLETED

- [x] 13. **Scheduler Base + Interfaces** ✅

  **What to do**:
  - Create `dlazy/scheduler/__init__.py` with exports
  - Update `dlazy/scheduler/base.py` (from Task 3):
    - Add `JobStatus` enum: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED, TIMEOUT, NODE_FAIL
    - Add `SubmitConfig` dataclass: job_name, nodes, ppn, time_limit, partition, qos
    - Add `SchedulerError` exception
    - Define interface methods with clear signatures
  - Write TDD tests for base class

  **Must NOT do**:
  - Don't add PBS/LSF abstract methods (SLURM only)
  - Don't add complex scheduling algorithms

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 14-20)
  - **Blocks**: Tasks 14-16

  **References**:
  - `dlazy/core/exceptions.py` - Exception hierarchy
  - `dlazy/scheduler/base.py` - Base from Task 3

  **Acceptance Criteria**:
  - [ ] `JobStatus` enum has all 7 states
  - [ ] `SubmitConfig` captures all SLURM parameters
  - [ ] All tests in `tests/test_scheduler_base.py` pass

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(scheduler): add scheduler base interfaces`
  - Files: `dlazy/scheduler/__init__.py`, `dlazy/scheduler/base.py`, `tests/test_scheduler_base.py`

- [x] 14. **SLURM Scheduler** ✅

  **What to do**:
  - Create `dlazy/scheduler/slurm.py`:
    - `SlurmScheduler` class implementing `Scheduler`
    - `submit(script_path: Path, config: SubmitConfig) -> str` - Submit job, return job_id
    - `check_status(job_id: str) -> JobStatus` - Query sacct/squeue
    - `cancel(job_id: str) -> bool` - Cancel job with scancel
    - `get_job_info(job_id: str) -> Dict` - Get detailed job info
    - Parse sacct output for job state
    - Handle job array notation
  - Write TDD tests (mock subprocess calls)

  **Must NOT do**:
  - Don't add PBS/LSF code
  - Don't use external SLURM libraries (direct sbatch/sacct/scancel)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13, 15-20)
  - **Blocks**: Task 21 (batch scheduler)

  **References**:
  - `dlazy/batch_workflow.py:_submit_slurm_job()` - Current SLURM submission
  - `dlazy/batch_workflow.py:_check_slurm_job_state()` - Current state check
  - SLURM documentation: `https://slurm.schedmd.com/documentation.html`

  **Acceptance Criteria**:
  - [ ] `SlurmScheduler.submit()` returns job_id on success
  - [ ] `SlurmScheduler.check_status()` returns correct JobStatus
  - [ ] `SlurmScheduler.cancel()` works correctly
  - [ ] All tests in `tests/test_slurm_scheduler.py` pass

  **QA Scenarios**:
  ```
  Scenario: Mock SLURM submit
    Tool: Bash (python)
    Steps:
      1. python -c "
from unittest.mock import patch, MagicMock
from dlazy.scheduler.slurm import SlurmScheduler
from dlazy.scheduler.base import SubmitConfig

with patch('subprocess.run') as mock_run:
    mock_run.return_value = MagicMock(returncode=0, stdout='Submitted batch job 12345')
    scheduler = SlurmScheduler()
    config = SubmitConfig(job_name='test', nodes=1, ppn=24, time_limit='1:00:00')
    job_id = scheduler.submit('/tmp/script.sh', config)
    print(f'job_id={job_id}')
"
    Expected: job_id=12345
    Evidence: .sisyphus/evidence/task-14-slurm-submit.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(scheduler): add SLURM scheduler`
  - Files: `dlazy/scheduler/slurm.py`, `tests/test_slurm_scheduler.py`

- [x] 15. **Job Manager** ✅

  **What to do**:
  - Create `dlazy/scheduler/job_manager.py`:
    - `JobManager` class:
      - `submit_job(script_path, config) -> str` - Submit and track
      - `wait_for_completion(job_id, timeout, poll_interval) -> JobStatus`
      - `get_active_jobs() -> List[str]`
      - `cancel_all() -> None`
      - Integration with `TaskStateStore` for state updates
    - Handle job state transitions
    - Track job metadata
  - Write TDD tests

  **Must NOT do**:
  - Don't add job scheduling logic (just management)
  - Don't add resource allocation

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13-14, 16-20)
  - **Blocks**: Task 21 (batch scheduler)

  **References**:
  - `dlazy/scheduler/slurm.py` - SlurmScheduler
  - `dlazy/state/task_state.py` - TaskStateStore

  **Acceptance Criteria**:
  - [ ] `JobManager` tracks active jobs
  - [ ] `wait_for_completion()` handles all terminal states
  - [ ] State updates propagated to TaskStateStore
  - [ ] All tests in `tests/test_job_manager.py` pass

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(scheduler): add job manager`
  - Files: `dlazy/scheduler/job_manager.py`, `tests/test_job_manager.py`

- [x] 16. **Resource Monitor** ✅

  **What to do**:
  - Create `dlazy/scheduler/resource_monitor.py`:
    - `ResourceMonitor` class:
      - `get_queue_status() -> Dict[str, int]` - Jobs per state
      - `get_node_status() -> Dict[str, str]` - Node availability
      - `get_user_jobs() -> List[Dict]` - Current user's jobs
      - `estimate_wait_time(job_config) -> float` - Estimate queue wait
    - Parse squeue/sinfo output
  - Write TDD tests (mock subprocess)

  **Must NOT do**:
  - Don't add resource allocation logic
  - Don't add predictive scheduling

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13-15, 17-20)
  - **Blocks**: None (optional feature)

  **References**:
  - `dlazy/workflow.py:_get_running_jobs()` - Similar functionality
  - SLURM squeue/sinfo documentation

  **Acceptance Criteria**:
  - [ ] `get_queue_status()` returns counts by state
  - [ ] `get_user_jobs()` returns current user's jobs
  - [ ] All tests in `tests/test_resource_monitor.py` pass

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(scheduler): add resource monitor`
  - Files: `dlazy/scheduler/resource_monitor.py`, `tests/test_resource_monitor.py`

- [x] 17. **Executor Base** ✅

  **What to do**:
  - Create `dlazy/executor/__init__.py` with exports
  - Update `dlazy/executor/base.py` (from Task 3):
    - `ExecutorContext` dataclass: config, workdir, stage, monitor
    - `TaskResult` dataclass: status, output_path, errors, validation_results
    - `Executor` abstract methods:
      - `prepare(task: Task) -> Path` - Prepare working directory
      - `execute(task: Task, ctx: ExecutorContext) -> TaskResult`
      - `validate(result: TaskResult) -> ValidationResult`
      - `cleanup(task: Task) -> None`
  - Write TDD tests

  **Must NOT do**:
  - Don't add stage-specific logic (in subclasses)
  - Don't add multiprocessing logic (in subclasses)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13-16, 18-20)
  - **Blocks**: Tasks 18-20

  **References**:
  - `dlazy/core/tasks.py` - Task data structures
  - `dlazy/contexts.py` - Existing context patterns

  **Acceptance Criteria**:
  - [ ] `ExecutorContext` captures all execution context
  - [ ] `TaskResult` includes validation results
  - [ ] All tests in `tests/test_executor_base.py` pass

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(executor): add executor base`
  - Files: `dlazy/executor/__init__.py`, `dlazy/executor/base.py`, `tests/test_executor_base.py`

- [x] 18. **OLP Executor** ✅

  **What to do**:
  - Create `dlazy/executor/olp.py`:
    - `OLPExecutor` class extending `Executor`
    - `prepare()` - Create working directory, link POSCAR
    - `execute()` - Run OpenMX overlap calculation
    - `validate()` - Use `HDF5IntegrityValidator` on overlaps.h5
    - `cleanup()` - Remove temporary files
  - Write TDD tests with mocked OpenMX

  **Must NOT do**:
  - Don't modify existing OpenMX execution logic (refactor only)
  - Don't add new OpenMX parameters

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13-17, 19, 20)
  - **Blocks**: Task 23 (integration tests)

  **References**:
  - `dlazy/commands.py:OLPCommandExecutor` - Current OLP logic
  - `dlazy/core/validator/hdf5_integrity.py` - Validator

  **Acceptance Criteria**:
  - [ ] `OLPExecutor.execute()` produces overlaps.h5
  - [ ] `OLPExecutor.validate()` checks HDF5 integrity
  - [ ] All tests in `tests/test_olp_executor.py` pass

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(executor): add OLP executor`
  - Files: `dlazy/executor/olp.py`, `tests/test_olp_executor.py`

- [x] 19. **Infer Executor** ✅

  **What to do**:
  - Create `dlazy/executor/infer.py`:
    - `InferExecutor` class extending `Executor`
    - `prepare()` - Link overlap files, transform data
    - `execute()` - Run DeepH inference
    - `validate()` - Use `HDF5IntegrityValidator` on hamiltonians.h5
    - `cleanup()` - Remove temporary files
  - Write TDD tests

  **Must NOT do**:
  - Don't modify DeepH inference logic
  - Don't add new inference parameters

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13-18, 20)
  - **Blocks**: Task 23 (integration tests)

  **References**:
  - `dlazy/commands.py:InferCommandExecutor` - Current Infer logic
  - `dlazy/core/validator/hdf5_integrity.py` - Validator

  **Acceptance Criteria**:
  - [ ] `InferExecutor.execute()` produces hamiltonians.h5
  - [ ] `InferExecutor.validate()` checks HDF5 integrity
  - [ ] All tests in `tests/test_infer_executor.py` pass

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(executor): add Infer executor`
  - Files: `dlazy/executor/infer.py`, `tests/test_infer_executor.py`

- [x] 20. **Calc Executor** ✅

  **What to do**:
  - Create `dlazy/executor/calc.py`:
    - `CalcExecutor` class extending `Executor`
    - `prepare()` - Link predicted Hamiltonians, create SCF input
    - `execute()` - Run OpenMX SCF calculation
    - `validate()` - Use `SCFConvergenceValidator` + `HDF5IntegrityValidator`
    - `cleanup()` - Remove temporary files
  - Write TDD tests

  **Must NOT do**:
  - Don't modify OpenMX SCF logic
  - Don't add new SCF parameters

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13-19)
  - **Blocks**: Task 23 (integration tests)

  **References**:
  - `dlazy/commands.py:CalcCommandExecutor` - Current Calc logic
  - `dlazy/core/validator/scf_convergence.py` - SCF validator
  - `dlazy/core/validator/hdf5_integrity.py` - HDF5 validator

  **Acceptance Criteria**:
  - [ ] `CalcExecutor.execute()` produces final hamiltonians.h5
  - [ ] `CalcExecutor.validate()` checks SCF convergence + HDF5 integrity
  - [ ] All tests in `tests/test_calc_executor.py` pass

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(executor): add Calc executor`
  - Files: `dlazy/executor/calc.py`, `tests/test_calc_executor.py`

---

### Wave 4: Integration + CLI ✅ COMPLETED (except cluster validation)

- [x] 21. **Batch Scheduler Refactor** ✅

  **What to do**:
  - Refactor `dlazy/batch_workflow.py:BatchScheduler`:
    - Use new `SlurmScheduler` instead of direct subprocess calls
    - Use `JobManager` for job tracking
    - Use `TaskStateStore` for state management
    - Use `CheckpointManager` for output verification
    - Use `RecoveryStrategyChain` for error handling
    - Integrate validators in `_collect_failed_tasks()`
  - Keep existing public API for backward compatibility
  - Write TDD tests

  **Must NOT do**:
  - Don't break existing CLI commands
  - Don't remove existing functionality

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO - Requires all previous tasks
  - **Parallel Group**: Sequential (after Waves 1-3)
  - **Blocks**: Tasks 22-24

  **References**:
  - `dlazy/batch_workflow.py` - Existing BatchScheduler
  - `dlazy/scheduler/slurm.py` - New scheduler
  - `dlazy/state/task_state.py` - State management
  - `dlazy/core/recovery/strategies.py` - Recovery strategies

  **Acceptance Criteria**:
  - [ ] `BatchScheduler` uses new modules internally
  - [ ] Existing tests pass
  - [ ] New tests cover integration points
  - [ ] All tests in `tests/test_batch_scheduler_v3.py` pass

  **Commit**: YES
  - Message: `refactor: integrate new modules into BatchScheduler`
  - Files: `dlazy/batch_workflow.py`, `tests/test_batch_scheduler_v3.py`

- [x] 22. **CLI Refactor with Rich** ✅

  **What to do**:
  - Refactor `dlazy/cli.py`:
    - Replace `print()` with Rich console
    - Add `RichProgress` to `batch` command
    - Add colored status output (green=success, red=error, yellow=warning)
    - Add structured table output for `batch-status`
    - Add `--verbose` flag for detailed output
  - Write TDD tests (capture Rich output)

  **Must NOT do**:
  - Don't add new CLI commands
  - Don't add Web UI

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [] (Rich library is straightforward)

  **Parallelization**:
  - **Can Run In Parallel**: NO - After Task 21
  - **Parallel Group**: Sequential
  - **Blocks**: Task 24 (user visible testing)

  **References**:
  - `dlazy/cli.py` - Current CLI
  - `dlazy/utils/progress.py` - Progress utilities
  - Rich documentation: `https://rich.readthedocs.io/`

  **Acceptance Criteria**:
  - [ ] `batch` command shows Rich progress bar
  - [ ] `batch-status` shows colored table
  - [ ] Error messages colored in red
  - [ ] All tests in `tests/test_cli_v3.py` pass

  **QA Scenarios**:
  ```
  Scenario: CLI shows progress bar
    Tool: Bash
    Steps:
      1. dlazy batch --config examples/test-workflow/global_config.yaml --batch-size 5
    Expected: Progress bar visible with task counts
    Evidence: .sisyphus/evidence/task-22-cli-progress.txt
  ```

  **Commit**: YES
  - Message: `feat(cli): add Rich progress and colored output`
  - Files: `dlazy/cli.py`, `tests/test_cli_v3.py`

- [x] 23. **Integration Tests** ✅

  **What to do**:
  - Create `tests/integration/` directory
  - Create end-to-end test scenarios:
    - `test_full_workflow.py` - Complete OLP→Infer→Calc workflow
    - `test_recovery.py` - Error recovery scenarios
    - `test_checkpoint_resume.py` - Resume from checkpoint
    - `test_concurrent_access.py` - Multiple process access
  - Use test fixtures for mock calculations
  - Add pytest markers: `@pytest.mark.integration`, `@pytest.mark.slow`

  **Must NOT do**:
  - Don't require real SLURM for integration tests
  - Don't use proprietary test data

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO - After Tasks 18-21
  - **Parallel Group**: Sequential
  - **Blocks**: Task 24, F3

  **References**:
  - `tests/fixtures/` - Test fixtures
  - `tests/conftest.py` - Shared fixtures

  **Acceptance Criteria**:
  - [ ] All integration tests pass
  - [ ] Coverage > 80% for new modules
  - [ ] `pytest tests/integration/ -v` shows all pass

  **Commit**: YES
  - Message: `test: add integration tests`
  - Files: `tests/integration/*.py`

- [ ] 24. **SLURM Cluster Validation**

  **What to do**:
  - SSH to `cpu.tj.th-3k.dkvpn`
  - Navigate to `/thfs4/home/xuyong/zeng/04.cluster/Ag_calc`
  - Run full workflow with small test data
  - Verify:
    - Job submission works
    - Job status tracking works
    - Error recovery works
    - Checkpoint/resume works
    - Progress bar displays correctly
  - Document any cluster-specific configurations needed

  **Must NOT do**:
  - Don't modify production data
  - Don't leave running jobs after testing

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO - Final validation
  - **Parallel Group**: Sequential (after all implementation)
  - **Blocks**: F3

  **References**:
  - `examples/test-workflow/` - Test configuration
  - Cluster documentation

  **Acceptance Criteria**:
  - [ ] Full workflow runs successfully on cluster
  - [ ] All stages complete with valid outputs
  - [ ] Error recovery tested (simulate failure)
  - [ ] Resume from interruption tested
  - [ ] Documentation updated with cluster notes

  **QA Scenarios**:
  ```
  Scenario: Full workflow on cluster
    Tool: interactive_bash (tmux)
    Steps:
      1. ssh cpu.tj.th-3k.dkvpn
      2. cd /thfs4/home/xuyong/zeng/04.cluster/Ag_calc
      3. dlazy batch --config global_config.yaml --batch-size 5
      4. Wait for completion
      5. dlazy batch-status --config global_config.yaml
    Expected: All tasks complete, status shows 100%
    Evidence: .sisyphus/evidence/task-24-cluster-run.txt

  Scenario: Resume from interruption
    Tool: interactive_bash (tmux)
    Steps:
      1. Start batch workflow
      2. Cancel job mid-execution (scancel)
      3. Re-run dlazy batch --config global_config.yaml
      4. Verify resumes from last checkpoint
    Expected: Resume without re-computing finished tasks
    Evidence: .sisyphus/evidence/task-24-cluster-resume.txt
  ```

  **Commit**: YES
  - Message: `docs: add cluster validation results`
  - Files: `docs/cluster-validation.md`

## Final Verification Wave (MANDATORY)

- [ ] F1. **Plan Compliance Audit** — `oracle`
- [ ] F2. **Code Quality Review** — `unspecified-high`
- [ ] F3. **Real Cluster E2E Test** — `unspecified-high`
- [ ] F4. **Scope Fidelity Check** — `deep`

---

## Commit Strategy

- **Per module**: `feat(scheduler): add SLURM scheduler module`
- **Tests with impl**: `feat(validator): add SCF convergence validator with tests`
- **Integration**: `feat: integrate all modules for batch workflow`

---

## Success Criteria

### Verification Commands
```bash
# Run all tests
pytest tests/ -v --cov=dlazy --cov-report=term-missing

# Test SLURM integration (requires cluster access)
pytest tests/test_slurm_integration.py -v --run-slurm

# Run batch workflow on test data
dlazy batch --config examples/test-workflow/global_config.yaml --batch-size 10

# Verify Rich progress
dlazy batch-status --config examples/test-workflow/global_config.yaml
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (pytest)
- [ ] Coverage > 80%
- [ ] SLURM cluster validation complete
