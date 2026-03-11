# deeplazy

Material calculation workflow automation system.

## Installation

```bash
# Local development installation
pip install -e .
```

## Usage

```bash
# Show version
deeplazy version

# Show help
deeplazy --help

# Run workflow
deeplazy run --config /path/to/global_config.yaml

# Check status
deeplazy status --config /path/to/global_config.yaml

# Stop workflow
deeplazy stop --config /path/to/global_config.yaml

# Restart workflow
deeplazy restart --config /path/to/global_config.yaml

# Run single stage (for debugging)
deeplazy olp --config /path/to/global_config.yaml --start 0 --end 10
deeplazy infer --config /path/to/global_config.yaml --group 1
deeplazy calc --config /path/to/global_config.yaml --start 0 --end 5

# Validate config file
deeplazy validate --config /path/to/global_config.yaml
```

## Workflow Stages

| Stage | Description | Input | Output |
|-------|-------------|-------|--------|
| `0olp` | Overlap calculation | POSCAR files | overlaps.h5 |
| `1infer` | DeepH inference | overlap files | predicted Hamiltonians |
| `2calc` | DFT recalculation | predicted Hamiltonians | accurate Hamiltonians |

## Configuration

See `examples/demo-workflow/global_config.yaml` for an example configuration file.

## Changelog

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
