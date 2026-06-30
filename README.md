# dlazy — minimal DFT workflow engine for DeepH co-optimization

`dlazy` orchestrates OpenMX SCF + DeepH inference workflows for generating training datasets from high-temperature structures. It manages job submission, restart, result collection, and export to DeepH training format.

## Workflow

```
POSCAR list → OLP (overlap) → DeepH inference → SCF (e6) → SCF (e7) → ... → collect
```

Each POSCAR in the structures list goes through:
1. **OLP** — Overlap-only OpenMX calculation → `overlap.h5`, `info.json`
2. **DeepH** — Neural network inference → `hamiltonian_pred.h5`
3. **SCF** — Self-consistent OpenMX with hamiltonian initial guess from DeepH or previous SCF step (multiple SCF steps with increasing convergence criteria)
4. **Collect** — Export final hamiltonian + overlap + POSCAR to DeepH training dataset format

## Install

```bash
pip install dpdispatcher pyyaml numpy h5py jinja2 pymatgen
git clone https://github.com/mingzhong15/deeplazy /path/to/deeplazy
pip install -e /path/to/deeplazy
```

Optional: install an OpenMX input generator for POSCAR → `openmx_in.dat` conversion (otherwise the `generator` module is imported at runtime and must resolve separately).

## CLI

```bash
dlazy run     <param.json> <machine.json> [--step NAME] [--dry-run]
dlazy collect <param.json> <machine.json> [--step NAME] [--all]
```

| Command | Description |
|---------|-------------|
| `run` | Execute the full workflow |
| `collect` | Export SCF results to `work_dir/deeph_datasets/<step>/` |
| `--step` | Limit to one step by name |
| `--dry-run` | (run only) Print tasks without submitting |
| `--all` | (collect only) Scan disk for **all** completed structures instead of reading the structures file |

## Input Files

### param.json

| Key | Required | Description |
|-----|----------|-------------|
| `name` | yes | Workflow name |
| `structures` | yes | Path to structures list file (relative to param.json) |
| `work_dir` | yes | Working directory for outputs |
| `steps` | yes | Ordered list of step definitions |
| `openmx` | no | Default OpenMX parameters, overridable per step |

Example:

```json
{
  "name": "al_high",
  "structures": "structures-360K.txt",
  "work_dir": "datasets/al",
  "openmx": {
    "max_iter": 200,
    "mixing_type": "RMM-DIISH",
    "scf_criterion": 1e-6
  },
  "steps": [
    { "name": "olp",  "type": "olp" },
    { "name": "infer","type": "deeph", "model": "/path/to/model" },
    { "name": "e6",   "type": "scf-restart", "scf_criterion": 1e-6, "init_from": "deeph" },
    { "name": "e7",   "type": "scf-restart", "scf_criterion": 1e-7, "init_from": "prev" }
  ]
}
```

#### Step types

| Type | Purpose | Key options |
|------|---------|-------------|
| `olp` | Overlap-only OpenMX | `force` (re-run) |
| `deeph` | DeepH inference | `model` (path to model dir), `force` (re-run) |
| `scf` | Self-consistent field | `scf_criterion`, `init_from` (`deeph`/`prev`/`none`), `startpulay`, `mixing_history`, `max_iter` |
| `scf-restart` | SCF requiring existing prediction | Same as `scf`; errors if DeepH prediction missing |

### Structures file

A text file listing POSCAR paths, one per line:

```
/path/to/Al_360K_0046.vasp
/path/to/Al_360K_0047.vasp
```

Structure IDs (`sid`) are the filename stems (e.g., `Al_360K_0046`). Multiple structures files can be prepared for different temperatures (e.g., `structures-360K.txt`, `structures-430K.txt`).

### machine.json

Defines the compute environment for dpdispatcher.

| Section | Description | Key fields |
|---------|-------------|------------|
| `machine` | HPC connection | `batch_type`, `context_type`, `local_root`, `remote_root` |
| `resources` | Job resources | `number_node`, `cpu_per_node`, `queue_name`, `group_size`, `custom_flags`, `source_list`, `envs` |
| `openmx` / `fp` | OpenMX binary | `executable`, `data_path`, `mpi_cmd`, `cpus_per_task` |
| `deeph` | DeepH binary | `executable`, `device`, `float_type`, `batch_size` |
| `job_name_prefix` | Slurm prefix | string |

## Directory Layout

```
work_dir/
├── restart/
│   ├── olp/<sid>/           # overlap.h5, info.json
│   ├── e6/<sid>/            # hamiltonians_step*.h5
│   └── e7/<sid>/            # (same)
├── inference/
│   ├── inputs/dft/<sid>/    # POSCAR symlink + overlap
│   └── outputs/<ts>/        # DeepH predictions
├── deeph_datasets/
│   ├── <step>/
│   │   ├── features.json
│   │   ├── <sid>/POSCAR, hamiltonian.h5, overlap.h5, info.json
│   └── <step>.tar.gz
└── record.dlazy              # step state tracking
```

## Collect and —all

```bash
# Normal: export only structures listed in the structures file
dlazy collect param.json machine.json

# Force: scan work_dir/restart/<step>/ for ALL completed structures on disk
dlazy collect param.json machine.json --all
```

`--all` infers POSCAR paths from the structures file's path pattern, so all POSCARs must reside in the same directory with `<sid>.vasp` naming. Missing POSCARs are skipped with a warning.
