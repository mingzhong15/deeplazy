# dlazy

Material calculation workflow automation system.

## Installation

```bash
# Local development installation
pip install -e .
```

## Usage

```bash
# Show version
dlazy version

# Show help
dlazy --help

# Run workflow
dlazy run --config /path/to/global_config.yaml

# Check status
dlazy status --config /path/to/global_config.yaml

# Stop workflow
dlazy stop --config /path/to/global_config.yaml

# Restart workflow
dlazy restart --config /path/to/global_config.yaml

# Run single stage (for debugging)
dlazy olp --config /path/to/global_config.yaml --start 0 --end 10
dlazy infer --config /path/to/global_config.yaml --group 1
dlazy calc --config /path/to/global_config.yaml --start 0 --end 5

# Validate config file
dlazy validate --config /path/to/global_config.yaml

# Batch workflow (for large-scale calculations)
dlazy batch --config /path/to/global_config.yaml --batch-size 100
dlazy batch --config /path/to/global_config.yaml --batch-size 50 --resume
dlazy batch-status --config /path/to/global_config.yaml
```

## Workflow Stages

| Stage | Description | Input | Output |
|-------|-------------|-------|--------|
| `0olp` | Overlap calculation | POSCAR files | overlaps.h5 |
| `1infer` | DeepH inference | overlap files | predicted Hamiltonians |
| `2calc` | DFT recalculation | predicted Hamiltonians | accurate Hamiltonians |

## Template System

Templates provide pre-configured workflow configurations for common tasks.

### List Available Templates

```bash
dlazy list-templates
```

### Run a Template

```bash
dlazy run --template openmx_olp --config global_config.yaml
```

### Available Templates

| Template | Description |
|----------|-------------|
| `openmx_olp` | OpenMX overlap calculation |
| `deeph_infer` | DeepH inference |
| `openmx_recal` | OpenMX DFT recalculation |

### Creating Custom Templates

Templates are YAML files located in `dlazy/templates/`. Each template defines the workflow configuration:

```yaml
name: openmx_olp
description: OpenMX overlap calculation template
stages:
  0olp:
    command: openmx ...
  1infer:
    command: deeph-infer ...
  2calc:
    command: openmx ...
```

See `dlazy/templates/` for examples.

## Batch Workflow

For large-scale structure calculations, use the batch workflow:

```bash
# Prepare todo_list.json (JSON Lines format, one POSCAR per line)
{"path": "/path/to/POSCAR_1", "elements": ["Al"], "n_atoms": [10]}
{"path": "/path/to/POSCAR_2", "elements": ["Cu"], "n_atoms": [20]}
...

# Configure in global_config.yaml:
# 0olp:
#   stru_log: "todo_list.json"  # default

# Run batch workflow
dlazy batch --config global_config.yaml --batch-size 100

# Resume from interruption
dlazy batch --config global_config.yaml --resume

# Check status
dlazy batch-status --config global_config.yaml
```

### Directory Structure

```
workflow_root/
├── todo_list.json              # Input: POSCAR paths (JSON Lines)
├── batch_state.json            # State file for resume
├── monitor_state.json          # Monitor state for error tracking
├── batch.00000/                # First batch
│   ├── slurm_olp/              # OLP SLURM scripts directory
│   │   ├── submit.sh           # SLURM submit script
│   │   ├── olp_tasks.jsonl     # OLP input tasks
│   │   ├── error_tasks.jsonl   # Failed OLP tasks
│   │   └── progress            # Progress tracking
│   ├── output_olp/             # OLP output directory
│   │   ├── folders.dat         # Task paths list
│   │   └── task.000000/        # Individual task output
│   │       └── overlaps.h5
│   ├── slurm_infer/            # Infer SLURM scripts directory
│   │   ├── submit.sh
│   │   ├── infer_tasks.jsonl   # Infer input tasks (from OLP)
│   │   ├── error_tasks.jsonl   # Failed Infer tasks
│   │   └── progress
│   ├── output_infer/           # Infer output directory
│   │   ├── hamlog.dat          # Task paths for Calc
│   │   └── g.001/              # Group directory
│   │       └── geth/
│   │           └── task.000000/
│   │               └── hamiltonians.h5
│   ├── slurm_calc/             # Calc SLURM scripts directory
│   │   ├── submit.sh
│   │   ├── calc_tasks.jsonl    # Calc input tasks (from Infer)
│   │   ├── error_tasks.jsonl   # Failed Calc tasks
│   │   └── progress
│   └── output_calc/            # Calc output directory
│       └── task.000000/
│           ├── scf/            # SCF calculation output
│           └── geth/hamiltonians.h5
├── batch.00001/                # Second batch
└── ...
```

### Task Record Format

All task files use JSON Lines format with unified field name `path`:

```json
{"path": "/path/to/POSCAR"}
{"path": "/path/to/POSCAR", "scf_path": "batch.00000/task.000000/olp"}
{"path": "/path/to/POSCAR", "geth_path": "batch.00000/task.000000/infer/geth"}
```

## Architecture & Data Flow

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    User Interface Layer                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│    $ dlazy batch --config global_config.yaml                                            │
│              │                                                                          │
│              ▼                                                                          │
│    __main__.py → cli.main() → argparse → args.func(args)                               │
│                                                                                         │
│    Commands: run/status/stop/restart | olp/infer/calc | batch/batch-status             │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                  Security Layer                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│    validate_path() → Check path traversal, dangerous patterns                           │
│    validate_global_config() → Validate all command templates                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                  Config Loading                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│    global_config.yaml → load_global_config_section() → deep_merge() → expand vars      │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                  Context Creation                                        │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│    BatchContext(config, workflow_root, batch_size, fresh, monitor)                      │
│    → OLPContext / InferContext / CalcContext (stage-specific)                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                               Batch Scheduler                                            │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│    BatchScheduler.run():                                                                │
│      1. _load_or_init_state() → Resume from batch_state.json                           │
│      2. _init_batch_tasks() → Split todo_list.json into batches                        │
│      3. Main loop: _run_stage(olp) → _run_stage(infer) → _run_stage(calc)             │
│      4. _collect_failed_tasks() → Output-based failure detection                       │
│      5. _forward_failed_tasks() → Relay to next batch                                  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
            ┌────────────────────────────┼────────────────────────────┐
            ▼                            ▼                            ▼
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│   OLP Stage (0olp)    │  │  Infer Stage (1infer) │  │  Calc Stage (2calc)   │
├───────────────────────┤  ├───────────────────────┤  ├───────────────────────┤
│  Input: olp_tasks     │  │  Input: infer_tasks   │  │  Input: calc_tasks    │
│  Process:             │  │  Process:             │  │  Process:             │
│   1. create_infile    │  │   1. Link OLP dir     │  │   1. create_infile    │
│   2. run_openmx       │  │   2. Transform        │  │   2. Link H predict   │
│   3. extract_overlap  │  │   3. Model Infer      │  │   3. run_openmx       │
│   4. validate_h5      │  │   4. Transform Rev.   │  │   4. check_conv       │
│  Output: overlaps.h5  │  │   5. validate_h5      │  │   5. extract_ham      │
│         infer_tasks   │  │  Output: hamiltonians │  │  Output: hamiltonians │
│                       │  │          calc_tasks   │  │                       │
└───────────────────────┘  └───────────────────────┘  └───────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                               State Persistence                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│    atomic_write_json() → Temp file → fsync → Atomic rename                              │
│    Files: batch_state.json, monitor_state.json, *_tasks.jsonl, error_tasks.jsonl       │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                  Error Handling                                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│    except WorkflowError → record_error() → error_tasks.jsonl                            │
│    if retry_count >= max → trigger_abort() → AbortException                            │
│    else → _forward_failed_tasks() → next batch                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Task Data Flow

```
OlpTask                    InferTask                      CalcTask
┌──────────────┐           ┌────────────────────┐         ┌────────────────────┐
│ path: str    │    →      │ path: str          │    →    │ path: str          │
│              │           │ scf_path: str      │         │ geth_path: str     │
│ (POSCAR路径) │           │ (OLP输出目录)      │         │ (Infer输出目录)    │
└──────────────┘           └────────────────────┘         └────────────────────┘
       │                           │                              │
       ▼                           ▼                              ▼
 olp_tasks.jsonl           infer_tasks.jsonl              calc_tasks.jsonl
```

### File System Data Flow

```
todo_list.json
       │
       │ _init_batch_tasks()
       ▼
batch.00000/
├── slurm_olp/
│   ├── submit.sh                    ← Template generated
│   ├── olp_tasks.jsonl              ← Split from todo_list.json
│   └── progress                     ← Progress tracking
│
├── output_olp/
│   └── task.000000/
│       └── overlaps.h5              ← OLP stage output
│
├── slurm_infer/
│   ├── submit.sh
│   └── infer_tasks.jsonl            ← OLP → Infer transfer
│
├── output_infer/
│   └── g.001/
│       ├── inputs/geth/task.000000/ ← Symlink to OLP output
│       └── geth/task.000000/
│           └── hamiltonians.h5      ← Infer stage output
│
├── slurm_calc/
│   ├── submit.sh
│   └── calc_tasks.jsonl             ← Infer → Calc transfer
│
└── output_calc/
    └── task.000000/
        ├── scf/hamiltonians.h5      ← Symlink from Infer (initial guess)
        └── geth/hamiltonians.h5     ← Final result
```

### Task Relay Mechanism

```
batch.00000 completed
       │
       ├─→ _collect_failed_tasks()
       │     ├─ OLP failure:   overlaps.h5 missing
       │     ├─ Infer failure: hamiltonians.h5 missing (in geth_path)
       │     └─ Calc failure:  hamiltonians.h5 missing (final)
       │
       └─→ _forward_failed_tasks()
             └─→ Append to batch.00001/slurm_olp/olp_tasks.jsonl
                   │
                   └─→ Exceeds total batches → permanent_errors.jsonl
```

### Utility Modules

| Module | Core Function | Role in Data Flow |
|--------|---------------|-------------------|
| **security.py** | Path/command validation | Ensure safe external inputs |
| **concurrency.py** | File locks, atomic writes | Concurrent-safe state persistence |
| **common.py** | Config loading, path resolution | Configuration management |
| **slurm_cache.py** | Job state caching | Reduce SLURM query overhead |
| **performance.py** | Performance monitoring | Identify bottlenecks |
| **contexts.py** | Context management | Thread-safe, testable design |

### Design Patterns

1. **Layered Architecture**: CLI → Command Handler → Scheduler → Executor → Utils
2. **Pipeline Pattern**: OLP → Infer → Calc three-stage workflow
3. **Relay Pattern**: Failed tasks automatically forwarded to next batch
4. **Resume Support**: State files enable workflow recovery
5. **Atomic Operations**: All state writes use atomicity guarantees
6. **Multi-layer Defense**: Path validation → Command validation → Argument escaping

## Configuration

See `examples/demo-workflow/global_config.yaml` for an example configuration file.

## Changelog

### v3.0.4 (2026-03-16)

**Bug Fix: Module Path Setup for SLURM**

- Added MODULEPATH setup after sourcing module init script
- Module paths need to include IO_tools, Libraries, etc.
- Fixes module loading failures in SLURM jobs

**Changes:**
- `dlazy/template_generator.py`: Set up MODULEPATH with all required directories
- Mimics /etc/profile.d/modules.sh behavior

### v3.0.3 (2026-03-16)

**Bug Fix: Direct Module Initialization for SLURM**

- Source module init script directly instead of relying on profile.d detection
- Add fallback path `/thfs4/software/modules/5.1.0/init/bash`
- Add error handling for module load failures
- Graceful degradation when modules not available

**Changes:**
- `dlazy/template_generator.py`: Direct source of module init bash script
- Prevents shell detection failures in SLURM environment

### v3.0.2 (2026-03-16)

**Bug Fix: SLURM Module Initialization**

- Fixed `module: command not found` error in SLURM non-interactive shells
- Added source of `/etc/profile.d/modules.sh` before module commands
- Critical for HPC clusters where module system isn't auto-initialized

**Changes:**
- `dlazy/template_generator.py`: `_format_modules()` now sources modules.sh first
- Ensures module commands work in all SLURM execution contexts

### v3.0.1 (2026-03-16)

**Bug Fix: xxhash Optional Dependency**

- Made `xxhash` import optional with automatic fallback to `hashlib.sha256`
- Prevents `ModuleNotFoundError` on systems without xxhash installed
- Maintains compatibility with environments that have xxhash (faster checksums)
- Critical for HPC clusters with restricted package installation

**Changes:**
- `dlazy/core/recovery/checksum.py`: Added try/except import with `XXHASH_AVAILABLE` flag
- New helper functions `_compute_xxh64()` and `_compute_sha256()` for cleaner code
- When xxhash unavailable, xxh64 algorithm falls back to sha256 automatically

### v3.0.0 (2026-03-15)

**Major Feature: Workflow Optimization System**

A comprehensive upgrade to the workflow system with enhanced scheduling, validation, and recovery capabilities. This release introduces a modular architecture for robust task execution on HPC clusters.

**New Module Structure:**
```
dlazy/
├── core/
│   ├── validator/           # Validation framework
│   │   ├── base.py          # Validator ABC, ValidationResult
│   │   ├── registry.py      # ValidatorRegistry
│   │   ├── scf_convergence.py   # SCFConvergenceValidator
│   │   └── hdf5_integrity.py    # HDF5IntegrityValidator
│   └── recovery/
│       ├── base.py          # RecoveryStrategy ABC
│       ├── checksum.py      # xxh64 checksum utilities
│       └── strategies.py    # RetryStrategy, SkipStrategy, AbortStrategy
├── scheduler/
│   ├── base.py              # Scheduler ABC, JobStatus, SubmitConfig
│   ├── slurm.py             # SlurmScheduler implementation
│   └── job_manager.py       # JobManager for lifecycle management
├── execution/
│   ├── base.py              # Executor ABC, TaskResult, ExecutorContext
│   ├── olp_executor.py      # OlpExecutor for OpenMX overlap
│   ├── infer_executor.py    # InferExecutor for DeepH inference
│   ├── calc_executor.py     # CalcExecutor for OpenMX SCF
│   └── factory.py           # create_executor() factory
└── state/
    ├── task_state.py        # TaskState, TaskStatus, TaskStateStore
    ├── checkpoint.py        # Checkpoint, CheckpointManager
    └── serializer.py        # StateSerializer for JSON persistence
```

**Key Features:**

1. **Scheduler System**
   - `SlurmScheduler`: Submit/check/cancel jobs with automatic retry logic
   - `JobManager`: Tracks job lifecycle, updates `TaskStateStore`, handles state transitions

2. **Validation Framework**
   - `SCFConvergenceValidator`: Checks OpenMX SCF convergence
   - `HDF5IntegrityValidator`: Validates HDF5 files (NaN/Inf/empty checks)
   - `ValidatorRegistry`: Extensible validator registration system

3. **Recovery Strategies**
   - `RetryStrategy`: For transient errors (node_error, timeout)
   - `SkipStrategy`: For permanent errors (config_error, security_error)
   - `AbortStrategy`: For critical errors (resource_error)
   - `RecoveryStrategyChain`: Ordered chain execution

4. **State Persistence**
   - `CheckpointManager`: Saves outputs with xxh64 checksums
   - `StateSerializer`: JSON serialization for TaskStateStore
   - `TaskStateStore`: State machine with transition validation

5. **Task Executors**
   - `OlpExecutor`: OpenMX overlap calculation
   - `InferExecutor`: transform → inference → transform_reverse pipeline
   - `CalcExecutor`: OpenMX SCF with convergence validation
   - `ExecutorFactory`: Stage-based executor creation

**Integration:**
- `WorkflowExecutor`: Added `use_new_executor` parameter (default False for backward compatibility)
- `BatchScheduler`: Automatically uses SlurmScheduler + JobManager + CheckpointManager

**Dependencies Added:**
- `rich>=13.0.0`: Progress bars and rich output
- `xxhash>=3.0.0`: Fast checksum computation

**Testing:**
- Comprehensive test suite with pytest
- TDD development approach throughout

### v2.14.2 (2026-03-14)

**Critical Bug Fixes:**
- Fixed `source_batch` and `retry_count` not propagated during stage transitions (OLP→Infer, Infer→Calc)
- Fixed Calc stage exception being swallowed instead of re-raised
- Fixed all errors written to OLP error file regardless of actual stage

**Data Flow Improvements:**
- Added `scf_path` field to CalcTask for full traceability
- Added parameter validation at CLI layer (start/end, group)
- Added Context validation via `__post_init__` (num_cores, parallel, model_dir existence)

**State Management Fixes:**
- Added FileLock protection for state file reads/writes
- Fixed non-atomic JSONL overwrite operations
- Fixed monitor state save using atomic_write_json

**Error Handling:**
- Unified error record format (message + error fields for backward compatibility)
- Improved error file routing by stage

### v2.12.0 (2026-03-14)

**Feature: Task Tracking & Statistics Improvement**

1. **Extended Task Data Structure**
   - Added `source_batch` field to track task origin (-1 = original, N = from batch N)
   - Added `retry_count` field to track retry attempts
   - Applied to OlpTask, InferTask, CalcTask

2. **Improved Relay Logic**
   - Failed tasks now carry source information when forwarded
   - Permanent failure based on `retry_count >= MAX_RETRY_COUNT` instead of batch index

3. **Better Statistics Display**
   - Distinguish original tasks vs relay tasks: `200 (173+27)` = 173 original + 27 relay
   - Show processing count: `处理次数: 2008 (原始 1557 + 中继 451)`
   - Clearer batch status with per-batch breakdown

4. **Infer Executor Improvements**
   - Warning when auxiliary files missing (info.json, POSCAR)
   - Node error detection and reporting
   - Better error messages for debugging

**Bug Fixes:**
- Fixed import paths after module refactoring (dlazy.record_utils → dlazy.core.tasks)
- Added `report_error()` method for backward compatibility
- Fixed `validate_path()` to default to cwd for relative paths

### v2.11.0 (2026-03-13)

**Documentation: Architecture & Data Flow**

Added comprehensive documentation for project core architecture:
- System architecture diagram (7 layers: CLI → Security → Config → Context → Scheduler → Executors → State)
- Task data flow (OlpTask → InferTask → CalcTask)
- File system data flow with directory structure
- Task relay mechanism for failed task retry
- Utility modules overview table
- Design patterns summary (6 patterns)

**Major Refactoring: Module Consolidation**

Unified error handling and utility modules for better maintainability and reduced code duplication.

**New Module Structure:**
```
dlazy/
├── core/                     # Core modules
│   ├── exceptions.py         # Unified exception hierarchy
│   ├── tasks.py              # Task data structures (OlpTask, InferTask, CalcTask)
│   └── workflow_state.py     # Monitoring + Error handling + Retry logic
│
├── utils/                    # Utility modules
│   ├── security.py           # Path/command validation + Config validation
│   ├── concurrency.py        # File locks + Atomic operations + PID locks
│   ├── slurm_cache.py        # SLURM state caching
│   ├── performance.py        # Performance monitoring
│   └── common.py             # Common utility functions
```

**Merged Modules:**
| Before | After |
|--------|-------|
| exceptions.py, error_handler.py, monitor.py, record_utils.py | core/exceptions.py, core/workflow_state.py, core/tasks.py |
| security.py, config_validator.py | utils/security.py |
| file_lock.py, pid_lock.py, optimized_commands.py | utils/concurrency.py |
| utils.py | utils/common.py |

**Key Improvements:**
- `ErrorTask` + `TaskError` → unified `ErrorRecord` class
- `AbortException` now inherits from `WorkflowError` for consistent error handling
- File locks and PID locks consolidated in single module
- Security validation and config validation merged
- All old APIs preserved via aliases for backward compatibility

**Benefits:**
- Reduced module count: 16 → 11
- Eliminated code duplication across error handling
- Clearer module responsibilities
- Easier maintenance and testing

### v2.14.1 (2026-03-13)

**Bug Fix: SLURM Job Submission Retry**

- Added automatic retry mechanism for SLURM job submission
- Retries up to 3 times with 10-second delay between attempts
- Better handling of transient SLURM errors

### v2.14.0 (2026-03-13)

**Critical Fix: Output-Based Failure Detection**

Failed tasks are now detected by comparing input tasks with actual outputs at each stage, instead of relying on error_tasks.jsonl which may not exist for silent failures.

**How it works:**
```
For each batch:
  1. Read all input paths from olp_tasks.jsonl
  2. Check OLP outputs: output_olp/task.*/overlaps.h5
  3. Check Infer outputs: geth_path/hamiltonians.h5 (from calc_tasks.jsonl)
  4. Check Calc outputs: output_calc/task.*/geth/hamiltonians.h5
  5. Failed = Input - Calc success
  6. Determine failure stage for each failed task
  7. Write to error_tasks.jsonl for record
  8. Relay to next batch if not exceeded
```

**Stage Detection:**
- Tasks missing overlaps.h5 → OLP failure
- Tasks with overlaps.h5 but missing infer output → Infer failure  
- Tasks with infer output but missing calc output → Calc failure

**Statistics Output:**
```
Stage statistics: OLP=120/120, Infer=100/120, Calc=100/100
Wrote 20 error tasks to error_tasks.jsonl
Collected 20 failed tasks (0 permanent failures)
```

**Changes:**
- `_collect_failed_tasks()` now uses output-based detection
- Automatic error_tasks.jsonl generation for all failures
- Detailed stage-by-stage failure analysis

### v2.13.0 (2026-03-13)

**New Feature: Task Relay System**

Failed tasks are automatically forwarded to the next batch for retry. Tasks are marked as permanent failure only when the relay exceeds total batches.

**How it works:**
```
Initial: 704 tasks, batch_size=100 → total_batches=8

batch.000: 100 tasks → 20 failed → relay to batch.001
batch.001: 100+20 tasks → 15 failed → relay to batch.002
...
batch.007: 100+5 tasks → 8 failed → next_batch=8 >= total=8
                                    ↓
                            permanent failure
```

**Changes:**
- `_collect_failed_tasks()` now uses relay-based failure detection
- Tasks marked as permanent failure when `next_batch_index >= total_batches`
- Removed dependency on `MAX_RETRY_COUNT` for batch relay

**Usage:**
```bash
# Run batch workflow with automatic task relay
dlazy batch --config global_config.yaml

# Failed tasks automatically forward to next batch
# Only marked as permanent when relay exceeds total batches
```

### v2.12.1 (2026-03-13)

**Bug Fixes:**
- **Fixed --run not creating new batches** - Now correctly resets `initialized=False` before starting retry batches
- **State reset on retry** - Updates `start_batch_index` and `current_batch` to existing batch count

**Improvements:**
- **Progress bar width** - Increased from 20 to 30 characters for better visibility

**Data Flow on --run:**
```
dlazy batch-retry-tasks --run:
  1. Generate todo_list_retry.json
  2. Backup todo_list.json → todo_list.origin.{idx}
  3. Copy retry file to todo_list.json
  4. Reset batch_state.json {initialized: false, start_batch_index: N}
  5. Start new batches from batch.{N:05d}
```

### v2.12.0 (2026-03-13)

**Critical Data Flow Improvements:**
- **Preserve original task list** - `todo_list.origin` is created on first run and never modified
- **Incremental backup system** - Each retry creates `todo_list.origin.001`, `.002`, etc.
- **Accurate statistics** - `batch-status` now correctly shows original task count
- **JSON Lines output** - `todo_list_retry.json` uses JSON Lines format for better streaming

**Data Flow:**
```
First run:
  todo_list.json → todo_list.origin (backup, never modified)
  batch.00000 ~ batch.00007 created
  batch_state.json {original_task_count: 704, ...}

First retry (--run):
  todo_list_retry.json generated (JSON Lines format)
  todo_list.origin.001 created (backup before retry)
  todo_list.json ← todo_list_retry.json
  batch.00008 created

batch-status:
  Original tasks: 704 (from batch_state.json or todo_list.origin)
  Current tasks: 79 (from todo_list.json)
  Completed: 625 (from batch outputs)
```

**Usage:**
```bash
# First run - creates todo_list.origin backup
dlazy batch --config global_config.yaml

# Retry - creates incremental backup before replacing
dlazy batch-retry-tasks --config global_config.yaml --run

# Check status - shows accurate original task count
dlazy batch-status --config global_config.yaml
```

### v2.11.0 (2026-03-13)

**New Features:**
- **Smart batch continuation** - Automatically detects existing batch directories
- **Interactive mode selection** - Prompts user to choose append/overwrite when existing batches found
- **`--batch-mode` parameter** - New CLI option for batch mode: `auto`, `append`, `overwrite`
- **`--run` parameter for `batch-retry-tasks`** - Automatically starts new batch after extracting failed tasks

**Usage:**
```bash
# Smart mode - prompts if existing batches found (default)
dlazy batch --config global_config.yaml

# Force append mode - continue from existing batches
dlazy batch --config global_config.yaml --batch-mode append

# Force overwrite mode - delete all existing batches
dlazy batch --config global_config.yaml --batch-mode overwrite

# Extract failed tasks and auto-start new batch
dlazy batch-retry-tasks --config global_config.yaml --run
```

**Example Interactive Session:**
```
$ dlazy batch --config global_config.yaml

检测到已有批次: batch.00000 ~ batch.00007
请选择处理方式:
  [1] append    - 从 batch.00008 继续添加新批次
  [2] overwrite - 删除所有批次，从 batch.00000 重新开始
请输入选择 (1/2): 1

正在从 batch.00008 开始创建新批次...
```

### v2.10.0 (2026-03-13)

**New Features:**
- **Stable release** - `batch-retry-tasks` command now provides accurate statistics
- Comprehensive stage completion tracking across OLP/Infer/Calc
- Automatic extraction of failed tasks for retry

**Statistics Summary for test-v2.6:**
- Total tasks: 704
- OLP completed: 704 (100%)
- Infer completed: 625 (88.8%) - 79 failed
- Calc completed: 503 (79.0%) - 131 failed
- Failed tasks saved to `todo_list_retry.json`: 210 tasks

**Usage:**
```bash
# Extract failed tasks with detailed statistics
dlazy batch-retry-tasks --config global_config.yaml

# Output shows:
# OLP   :  704 →  704 (100.0%) ✓
# INFER :  704 →  625 ( 88.8%) - 79 failed
# CALC  :  625 →  494 ( 79.0%) - 131 failed
# 总计: 494/704 完成 (70.2%)
```

### v2.9.9 (2026-03-13)

**Bug Fixes:**
- **Fixed Infer statistics** - Now correctly tracks Infer completion using calc_tasks.jsonl
- Infer completion is determined by checking hamiltonians.h5 in geth_path (from calc_tasks.jsonl)
- Calc completion is determined by checking hamiltonians.h5 in output_calc/task.*/geth/

**Statistics Accuracy:**
- Previous v2.9.8 incorrectly showed Infer as 0% complete
- Now shows accurate completion rates for all three stages

### v2.9.8 (2026-03-13)

**Critical Bug Fixes:**
- **Fixed `batch-retry-tasks` statistics error** - Calc completion was incorrectly counting Infer outputs
- Now correctly counts OLP/Infer/Calc outputs from actual output directories:
  - OLP: `output_olp/task.*/overlaps.h5`
  - Infer: `output_infer/*/geth/*/hamiltonians.h5`
  - Calc: `output_calc/task.*/geth/hamiltonians.h5`

**Statistics Accuracy:**
- Previous version incorrectly reported Calc as 100% when only Infer completed
- Now shows accurate completion rates for each stage
- Correctly identifies which tasks need to be retried

### v2.9.7 (2026-03-13)

**New Features:**
- Added `dlazy batch-retry-tasks` command to extract uncompleted tasks from batch workflow
- Displays detailed completion statistics for all stages (OLP/Infer/Calc)
- Automatically generates `todo_list_retry.json` for failed tasks

**Improvements:**
- Enhanced stage completion tracking with clear statistics
- Better visibility into which tasks failed at which stage
- Simplified retry workflow for incomplete batch calculations

**Usage:**
```bash
# Extract failed tasks
dlazy batch-retry-tasks --config global_config.yaml

# Custom output file
dlazy batch-retry-tasks --config global_config.yaml --output my_retry_list.json
```

### v2.9.6 (2026-03-13)

**Critical Bug Fixes:**
- **Fixed batch workflow error recovery mechanism** - Failed tasks are now correctly written to `error_tasks.jsonl`
- All three stages (OLP/Infer/Calc) now properly record failed tasks for retry
- Error records use unified JSONL format: `{"path": "...", "stage": "...", "error": "...", "batch_id": "...", "task_id": "...", "retry_count": 0}`
- Failed tasks are now correctly forwarded to next batch for retry
- Permanent error marking (after 3 retries) now works as designed

**Architecture Improvements:**
- Created unified error handling module (`dlazy/error_handler.py`)
- `ErrorContext` and `record_error()` provide consistent error recording across all stages
- Eliminated run/batch mode error handling discrepancy
- All stages now use JSONL format for `error_tasks.jsonl`

**Testing:**
- Added `tests/test_error_recovery.py` for comprehensive error recovery testing
- Unit tests cover OLP/Infer/Calc failure scenarios
- Integration tests verify retry mechanism and permanent error marking

### v2.9.5 (2026-03-13)

**Bug Fixes:**
- Fixed Infer stage progress: removed duplicate "end" loop, added error tracking
- Unified progress label format: now uses absolute paths across OLP/Infer/Calc stages

**Enhancements:**
- Added batch time tracking: records start/end time for each batch
- Enhanced `batch-status` output:
  - Shows original tasks count from todo_list.json
  - Displays per-batch detailed status table
  - Shows success/failure/retry/permanent-failure statistics
  - Displays permanent failed tasks (exceeded max retries)
- Added `PERMANENT_ERRORS_FILE` constant for tracking failed tasks

**Constants:**
- `PERMANENT_ERRORS_FILE = "permanent_errors.jsonl"` - stores tasks that exceeded max retry count

### v2.9.4 (2026-03-13)

**Bug Fixes:**
- Fixed `batch-status` error count: now correctly reads from `slurm_{stage}/error_tasks.jsonl` instead of wrong path
- Removed unused dead code: `count_infer_outputs()`, `count_calc_outputs()` functions

**Documentation:**
- Updated directory structure in README to reflect actual implementation (`slurm_olp/`, `output_olp/`, etc.)

### v2.9.3 (2026-03-12)

**Bug Fixes:**
- Fixed `data_dir_depth` from 1 to 0 in infer.toml.j2 template (match transform `-t 0` output)
- Fixed Calc stage: now correctly reads `hamiltonians.h5` (transform_reverse output) instead of fallback lookup
- Added progress "end" tracking in Infer stage

### v2.9.2 (2026-03-12)

**Config Fix:**
- Fixed `transform_reverse` command parameter order in `global_config.yaml` example
- Correct order for `--backward` mode: `{input_dir}` (new format) before `{output_dir}` (old format)

### v2.9.1 (2026-03-12)

**Infer Stage Fix:**
- Fixed symlink source for `info.json`: now correctly links from `inputs/dft/` instead of `outputs/dft/`
- Added `POSCAR` symlink to `geth.new/` directory for transform_reverse

**Transform Reverse Fix:**
- `--backward` mode requires correct parameter order: `input_dir` (new format) before `output_dir` (old format)
- Update `global_config.yaml`: swap `{input_dir}` and `{output_dir}` in `transform_reverse` command

### v2.9.0 (2026-03-12)

**Auto-Resume Behavior:**
- `dlazy batch` now automatically resumes from saved state by default
- New `--fresh` flag to start from scratch (deletes existing state)
- No need for `--resume` flag anymore

**Infer Stage Fix:**
- Fixed `data_dir_depth` in `infer.toml.j2`: changed from 2 to 1
- Fixed transform command `-t` parameter guidance: use `-t 0` for current directory structure

**Usage Changes:**
```bash
# Auto-resume (default)
dlazy batch --config global_config.yaml

# Fresh start
dlazy batch --config global_config.yaml --fresh
```

### v2.7.1 (2026-03-12)

**Critical Fix:**
- Fixed output directory nesting issue: outputs now correctly go to `batch.00000/output_olp/` instead of `batch.00000/slurm_olp/0olp/`
- Added `workdir` parameter to all SLURM script generators (OLP/Infer/Calc)
- `BatchScheduler._run_stage()` now passes `workdir` to ensure correct output paths

**Expected Directory Structure:**
```
batch.00000/
├── slurm_olp/          # SLURM scripts only
│   ├── submit.sh
│   ├── olp_tasks.jsonl
│   └── slurm-*.out
├── output_olp/         # OLP outputs (correct location)
│   ├── folders.dat
│   ├── progress
│   └── ...task dirs...
├── slurm_infer/
├── output_infer/
└── ...
```

### v2.7.0 (2026-03-12)

**Batch Workflow Fixes:**
- SLURM scripts now correctly read `olp_tasks.jsonl` and `calc_tasks.jsonl` instead of `global_config.stru_log`
- Added `tasks_file` parameter to SLURM script generators for explicit task file paths
- Modified `_read_calc_records` to support JSON Lines format (`calc_tasks.jsonl`)

**PID Management:**
- Added PID file management for `dlazy batch` command (`pid.batch`)
- Added `dlazy batch-stop` command to stop running batch workflows
- Enhanced `dlazy batch-status` with detailed progress and error information
- Added signal handlers for graceful shutdown (SIGTERM, SIGINT)
- Shows PID on startup for monitoring

**New Constants:**
- `STAGE_TASKS_FILE_MAP`: maps stage names to task file names
- `BATCH_PID_FILE`, `BATCH_LOG_FILE`: for batch workflow management

### v2.4.0 (2026-03-12)

**Unified Record Format:**
- Unified field name: `poscar_path` → `path` across all task records
- All task files now use consistent JSON Lines format
- Input file format changed: `poscar_list.txt` → `todo_list.json` (JSON Lines)
- Read input file from config: `stru_log` parameter in `0olp` section

**Batch Workflow Improvements:**
- Fixed infinite loop issue: workflow now exits properly when no tasks remain
- Pre-check tasks before processing each batch
- Better error messages when input file not found

**Breaking Changes:**
- `poscar_path` field renamed to `path` in all task records
- Input file format changed from plain text to JSON Lines
- Old `poscar_list.txt` no longer supported

### v2.3.2 (2026-03-17)

**Critical Performance Fix:**

1. **Fixed Calc stage MPI parallelization issue**
   - Root cause: Complex module initialization in submit.sh interfered with SLURM environment
   - Simplified `_format_modules()` to avoid environment variable interference
   - Added `num_cores` and `max_processes` attributes to `CalcContext`
   - Modified `CalcCommandExecutor.execute` and `execute_batch` to pass `ntasks` parameter
   - Performance improvement: **~30x faster** (2 min vs 60 min per task)

2. **Module initialization simplified** (`template_generator.py:12-22`)
   - Removed explicit `source /thfs4/software/modules/.../bash`
   - Let system default module initialization handle environment setup
   - Prevents interference with SLURM's environment variables

**Configuration Update Required:**

Users should update their `global_config.yaml`:
```yaml
2calc:
  num_cores: 64           # Add this
  max_processes: 1        # Add this
  commands:
    run_openmx: yhrun --ntasks={ntasks} {openmx_restart} openmx_in.dat >> openmx.std 2>&1
```

**Impact:**
- OpenMX now correctly uses all allocated CPU cores (64 MPI processes instead of 1)
- Dramatically faster calculation times for DFT recalculation stage

### v2.3.1 (2026-03-17)

**Critical Bug Fixes:**

1. **Fixed SLURM array job state detection bug** (`batch_workflow.py:586-632`)
   - Previously only checked the first sub-job state, causing premature stage transitions
   - Now correctly aggregates all sub-job states:
     - Returns `RUNNING` if any sub-job is still running/pending
     - Returns `FAILED` if any sub-job failed (and none running)
     - Returns `COMPLETED` only if all sub-jobs completed successfully
   - This fix prevents calc stage from starting before infer tasks complete

2. **Fixed batch_status update delay** (`batch_workflow.py:634-676`)
   - Added `job_state` field to batch_state.json during polling loop
   - `last_update` now reflects actual monitoring activity, not just stage transitions

**Impact:**
- Prevents incomplete task files being read by subsequent stages
- Ensures all array sub-jobs complete before advancing to next stage
- Better visibility of job monitoring status

### v2.3.0 (2026-03-11)

**Monitor Integration:**
- Integrated `JobMonitor` into `BatchWorkflowManager` for error tracking
- Added `FailureType` enum and `AbortException` for error classification
- Added monitor state persistence (`monitor_state.json`)
- Added automatic abort on max retries exceeded

**Package Rename:**
- Renamed package from `deeplazy` to `dlazy` for shorter CLI commands
- CLI command changed: `deeplazy` → `dlazy`

**New Exports:**
- `BatchContext`, `FailureType`, `AbortException` added to `__init__.py`

### v2.2.0 (2026-03-11)

**Package Rename:**
- Renamed package from `deeplazy` to `dlazy` for shorter CLI commands
- CLI command changed: `deeplazy` → `dlazy` (e.g., `dlazy run`, `dlazy olp`)
- Updated all imports: `from deeplazy` → `from dlazy`
- Updated template generator: `deeplazy_path` → `dlazy_path`

**Batch Workflow:**
- Added `BatchWorkflowManager` for large-scale structure calculations
- Added deterministic directory structure: `batch.NNNNN/task.NNNNNN/{olp,infer,scf}/`
- Added JSON Lines record format for task tracking
- Added `dlazy batch` and `dlazy batch-status` CLI commands
- Added resume support via `--resume` flag

**New Files:**
- `record_utils.py` - Unified record format (OlpTask, InferTask, CalcTask, ErrorTask)
- `batch_workflow.py` - BatchWorkflowManager implementation
- `monitor.py` - JobMonitor for error tracking and retry logic

**New Constants:**
- `OLP_TASKS_FILE`, `INFER_TASKS_FILE`, `CALC_TASKS_FILE`, `ERROR_TASKS_FILE`
- `BATCH_STATE_FILE`, `BATCH_DIR_PREFIX`, `TASK_DIR_PREFIX`
- `OLP_SUBDIR`, `INFER_SUBDIR`, `SCF_SUBDIR`
- `DEFAULT_MAX_RETRIES`, `MONITOR_STATE_FILE`

### v2.1.0 (2026-03-11)

**Executor improvements:**
- Added structured logging for all workflow stages (OLP, Infer, Calc)
- Added exception handling with error logging in `run_infer_stage`

**Commands improvements:**
- Added `_cleanup_directory()` and `_ensure_symlink()` helper functions
- Changed `label` in OLP stage to use full POSCAR path (for consistent folders.dat output)
- Refactored `_link_overlap_files()` to link entire directories instead of single files
- Added comprehensive logging throughout Infer stage execution
- Added try/except with error file writing in `InferCommandExecutor.execute`
- Added logger parameter to all Infer helper methods
- Improved error reporting with detailed failure messages

**Logging format:**
- Consistent logger naming: `restart_workflow.3steps.executor.{stage}` and `restart_workflow.3steps.infer.group{N}`

### v2.0.0

- Initial release with modular architecture
- Three-stage workflow: OLP → Infer → Calc
- CLI interface with argparse
- SLURM job script generation

## Development

```bash
# Run tests
python -m pytest tests/

# Or directly
python tests/test_cli.py
```
