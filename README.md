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

## Configuration

See `examples/demo-workflow/global_config.yaml` for an example configuration file.

## Changelog

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
