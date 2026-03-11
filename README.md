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

## Development

```bash
# Run tests
python -m pytest tests/

# Or directly
python tests/test_cli.py
```
