# dlazy — minimal DFT workflow engine for DeepH co-optimization

`dlazy` orchestrates OpenMX SCF + DeepH inference workflows for generating training datasets from high-temperature structures. It manages job submission, restart, result collection, and export to DeepH training format.

Two operating modes:
- **easy** (default): one dpdispatcher Task per structure, submitted as individual Slurm jobs. Best for small batches (<100 structures).
- **massive**: uses dpdispatcher `SlurmJobArray` to submit one `sbatch --array=0-N` covering all structures. Each array element runs `dlazy/_runner.py` over a manifest of K structures (serial for SCF, parallel for OLP). Best for high-throughput (1000+ structures, 500+ nodes).

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
              [--retry-failed] [--only-sids sid1,sid2]
dlazy collect <param.json> <machine.json> [--step NAME] [--all]
```

| Command | Description |
|---------|-------------|
| `run` | Execute the full workflow |
| `collect` | Export SCF results to `work_dir/deeph_datasets/<step>/` |
| `--step` | Limit to one step by name |
| `--dry-run` | (run only) Print tasks without submitting |
| `--retry-failed` | (run only, massive mode) Retry only sids marked `fail` in `restart/<step>/_status/_summary.ndjson`. Requires `--step`. |
| `--only-sids` | (run only) Run only these sids (comma-separated). Works in both modes. |
| `--all` | (collect only) Scan disk for **all** completed structures instead of reading the structures file |

### Operating modes

Set `mode` in `param.json`:

| Mode | Description |
|------|-------------|
| `easy` (default) | One dpdispatcher Task per structure, individual Slurm jobs. Backward compatible. |
| `massive` | One Slurm `--array` job per step. Each array element = 1 manifest of K structures run via `dlazy/_runner.py`. Per-sid status written atomically to `restart/<step>/_status/<sid>.json` and `restart/<step>/_status/_summary.ndjson`. Enables `--retry-failed` and stable `submission_hash` across re-runs. |

## Input Files

### param.json

| Key | Required | Description |
|-----|----------|-------------|
| `name` | yes | Workflow name |
| `structures` | yes | Path to structures list file (relative to param.json) |
| `work_dir` | yes | Working directory for outputs |
| `mode` | no | `"easy"` (default) or `"massive"` |
| `steps` | yes | Ordered list of step definitions |
| `openmx` | no | Default OpenMX parameters, overridable per step |

Example (easy mode):

```json
{
  "name": "al_high",
  "structures": "structures-360K.txt",
  "work_dir": "datasets/al",
  "mode": "easy",
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

Massive mode: just set `"mode": "massive"`. Step definitions stay the same; dlazy switches the dispatcher to `SlurmJobArray` and bundles structures into per-step manifests of `tasks_per_array` (from `machine.json` `massive` section).

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
| `olp` | OpenMX binary for OLP step | `executable`, `data_path`, `mpi_cmd`, `nprocs`, `nworkers` |
| `fp` | OpenMX binary for SCF steps | `executable`, `data_path`, `mpi_cmd`, `cpus_per_task` |
| `deeph` | DeepH binary | `executable`, `device`, `float_type`, `batch_size` |
| `massive` | Massive-mode scheduling | `tasks_per_array` (K sids per array element), `group_size` (override) |
| `job_name_prefix` | Slurm prefix | string |

In massive mode dlazy forces `batch_type=SlurmJobArray` and sets `resources.kwargs.slurm_job_size=1`, so each Task (each manifest) becomes one array element. The `machine.batch_type` field in `machine.json` is overridden; users only need to add the `massive` section.

## Directory Layout

```
work_dir/
├── restart/
│   ├── olp/<sid>/           # overlap.h5, info.json
│   ├── e6/<sid>/            # hamiltonians_step*.h5
│   └── e7/<sid>/            # (same)
│   └── e6/_status/          # (massive mode only) per-sid status files
│       ├── <sid>.json       # {"sid":"...", "state":"ok|fail", "walltime":N}
│       └── _summary.ndjson  # one line per sid completion (rerun-safe)
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

## Massive Mode

Switch to `mode = "massive"` in `param.json` for high-throughput (1000+ structures):

```bash
# Initial run: one sbatch --array=0-N covers all structures
dlazy run param.json machine.json --step e6

# Retry only failed sids (re-runs just the failed manifests)
dlazy run param.json machine.json --step e6 --retry-failed

# Re-run a specific subset
dlazy run param.json machine.json --step e6 --only-sids sid1,sid2,sid3
```

### How it works

1. `param.mode = "massive"` makes `Workflow` load `SlurmJobArray` (dpdispatcher built-in) and set `resources.kwargs.slurm_job_size = 1`.
2. Each step's `prepare()` batches structures into K-sized manifests (`massive.tasks_per_array`), one dpdispatcher Task per manifest.
3. dpdispatcher submits one `sbatch --array=0-N` covering all manifest Tasks.
4. Each array element invokes `dlazy/_runner.py --manifest ... --mode serial|parallel`:
   - SCF: serial loop over K sids (avoids MPI contention per node)
   - OLP: `multiprocessing.Pool(K)` parallel
5. Runner writes per-sid status atomically to `restart/<step>/_status/<sid>.json` and appends a one-line JSON to `restart/<step>/_status/_summary.ndjson` (O_APPEND + fsync, NFS-safe).
6. `engine._aggregate_status` reads the single summary file (O(1) IO) to display live `ok:K fail:L/total` during polling.
7. `--retry-failed` reads the summary, filters prepare() to only failed sids.

### Submission hash stability

In massive mode, `prepare()` does NOT skip already-finished sids when building the manifest list (it includes all sids in `structures.txt`). This keeps `submission_hash` stable across re-runs so dpdispatcher's `try_recover_from_json` works. The wf_runner skips `state == "ok"` sids at execution time, so already-finished structures are not recomputed.

If `wf_runner.py` content changes (e.g., dlazy upgrade), the hash will differ - dpdispatcher will create a fresh submission. The runner still skips ok sids via `_status/<sid>.json`, so no work is wasted.
