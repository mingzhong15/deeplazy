"""Node-local runner invoked by SlurmJobArray array elements in massive mode.

Called by dpdispatcher-generated Slurm script per array element. Each
element corresponds to one dpdispatcher Task, which corresponds to one
manifest of K structures. The runner reads the manifest and either:
  - serial:   for sid in sids: cd restart/<step>/<sid> && mpi openmx ...
  - parallel: multiprocessing.Pool(nworkers).map(run_one, sids)

Per-sid status is written atomically to restart/<step>/_status/<sid>.json
and a one-line summary appended to restart/<step>/_status/_summary.ndjson
so engine.gather_status can read O(1) files instead of O(N).

Exit code is 0 only if every sid either finished normally (openmx.std
contains 'normally finished') or was already ok from a prior run; any
failure gives exit 1 so dpdispatcher marks the array element terminated
and SlurmJobArray retries it (skipping sids already marked ok).
"""
import argparse
import json
import multiprocessing
import os
import subprocess
import sys
import time
from pathlib import Path


def _atomic_write_json(path: Path, data: dict):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def _append_summary(summary_path: Path, line: str):
    """Atomic append in O_APPEND mode. Each line is one sid's status JSON."""
    with open(summary_path, "a") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def _run_one(args):
    """Run a single structure's SCF/OLP. Called either directly or via Pool.

    args = (sid, step_dir_abs, step, work_dir_abs, mpi_cmd, nprocs, exe)
    Returns (sid, ok_bool, walltime_sec).
    """
    sid, step_dir_abs, step, work_dir_abs, mpi_cmd, nprocs, exe = args
    step_path = Path(step_dir_abs)
    status_dir = step_path.parent / "_status"
    status_file = status_dir / f"{sid}.json"
    summary_file = status_dir / "_summary.ndjson"

    if status_file.exists():
        try:
            prev = json.loads(status_file.read_text())
            if prev.get("state") == "ok":
                return sid, True, 0.0
        except Exception:
            pass

    if not (step_path / "openmx_in.dat").exists():
        _atomic_write_json(status_file, {"sid": sid, "state": "fail",
                                          "reason": "missing openmx_in.dat"})
        _append_summary(summary_file, json.dumps({"sid": sid, "state": "fail"}))
        return sid, False, 0.0

    cmd = mpi_cmd.replace("{cpus}", str(nprocs))
    cmd = f"{cmd} {exe} openmx_in.dat > openmx.std 2>&1"
    t0 = time.time()
    try:
        result = subprocess.run(cmd, shell=True, cwd=str(step_path),
                                capture_output=True, text=True, timeout=None)
        walltime = time.time() - t0
        # Success if openmx reported "normally finished" OR if the
        # expected output artifact exists (overlap.h5 for OLP,
        # hamiltonians_step*.h5 for SCF). The latter is more lenient
        # and matches dlazy.utils.check_finished semantics.
        std_ok = _check_finished(step_path / "openmx.std")
        artifact_ok = (step_path / "overlap.h5").exists() or \
            any(step_path.glob("hamiltonians_step*.h5"))
        ok = result.returncode == 0 and (std_ok or artifact_ok)
        state = "ok" if ok else "fail"
        _atomic_write_json(status_file, {
            "sid": sid, "state": state,
            "returncode": result.returncode,
            "walltime": walltime,
        })
        _append_summary(summary_file, json.dumps({"sid": sid, "state": state}))
        return sid, ok, walltime
    except Exception as e:
        walltime = time.time() - t0
        _atomic_write_json(status_file, {"sid": sid, "state": "fail",
                                          "reason": str(e), "walltime": walltime})
        _append_summary(summary_file, json.dumps({"sid": sid, "state": "fail"}))
        return sid, False, walltime


def _check_finished(std_path):
    """Same logic as dlazy.utils.check_finished but standalone (no import)."""
    p = Path(std_path)
    if not p.exists():
        return False
    return "normally finished" in p.read_text()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--mpi", required=True)
    parser.add_argument("--nprocs", type=int, required=True)
    parser.add_argument("--mode", choices=["serial", "parallel"], default="serial")
    parser.add_argument("--nworkers", type=int, default=1)
    args = parser.parse_args()

    with open(args.manifest) as f:
        manifest = json.load(f)
    sids = manifest["sids"]
    step = manifest["step"]
    work_dir = manifest["work_dir"]

    step_dir_abs = os.path.join(work_dir, "restart", step)
    status_dir = os.path.join(step_dir_abs, "_status")
    os.makedirs(status_dir, exist_ok=True)

    batch = [(sid, os.path.join(step_dir_abs, sid), step, work_dir,
              args.mpi, args.nprocs, args.exe) for sid in sids]

    print(f"[RUNNER] mode={args.mode} step={step} sids={len(sids)} "
          f"nprocs={args.nprocs} nworkers={args.nworkers}", flush=True)

    if args.mode == "parallel":
        with multiprocessing.Pool(args.nworkers) as pool:
            results = pool.map(_run_one, batch)
    else:
        results = [_run_one(b) for b in batch]

    failed = [sid for sid, ok, _ in results if not ok]
    ok_count = sum(1 for _, ok, _ in results if ok)
    total_wall = sum(w for _, _, w in results)
    print(f"[RUNNER] ok={ok_count}/{len(sids)} fail={len(failed)} "
          f"walltime={total_wall:.1f}s", flush=True)

    if failed:
        print(f"[RUNNER] failed: {failed[:10]}", flush=True)
        sys.exit(1)
    print(f"[RUNNER] all {len(sids)} sids completed", flush=True)


if __name__ == "__main__":
    main()
