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
# Prepare poscar_list.txt with POSCAR paths (one per line)
/path/to/POSCAR_1
/path/to/POSCAR_2
...

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
├── poscar_list.txt           # Input: POSCAR paths
├── batch_state.json          # State file for resume
├── monitor_state.json        # Monitor state for error tracking
├── batch.00000/              # First batch
│   ├── olp_tasks.jsonl       # OLP input tasks
│   ├── infer_tasks.jsonl     # Infer input tasks (OLP output)
│   ├── calc_tasks.jsonl      # Calc input tasks (Infer output)
│   ├── error_tasks.jsonl     # Failed tasks
│   └── task.000000/          # Individual task
│       ├── olp/              # OLP stage output
│       ├── infer/            # Infer stage output
│       └── scf/              # Calc stage output
├── batch.00001/              # Second batch
└── ...
```

## Configuration

See `examples/demo-workflow/global_config.yaml` for an example configuration file.

## Changelog

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
