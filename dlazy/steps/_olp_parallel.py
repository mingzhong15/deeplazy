import argparse
import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path


def run_one_structure(args):
    sid, step_dir, mpi_cmd, ntasks, exe = args
    step_path = Path(step_dir)
    os.chdir(str(step_path))
    cmd = mpi_cmd.replace("{cpus}", str(ntasks))
    cmd = f"{cmd} {exe} openmx_in.dat > openmx.std 2>&1"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    ok = result.returncode == 0 and (step_path / "overlap.h5").exists()
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {sid}")
    if not ok:
        print(f"  returncode={result.returncode}, overlap.h5 exists={(step_path / 'overlap.h5').exists()}")
    return sid, ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--mpi", required=True)
    parser.add_argument("--nprocs", type=int, required=True)
    parser.add_argument("--nworkers", type=int, required=True)
    args = parser.parse_args()

    with open(args.manifest) as f:
        manifest = json.load(f)
    work_dir = manifest["work_dir"] if isinstance(manifest, dict) else os.path.abspath(os.path.dirname(args.manifest))
    sids = manifest["sids"] if isinstance(manifest, dict) else manifest

    batch = [(sid, os.path.join(work_dir, "restart", "olp", sid),
              args.mpi, args.nprocs, args.exe) for sid in sids]

    print(f"[BATCH] {len(sids)} structures, {args.nworkers} workers, {args.nprocs} cores/task")

    with multiprocessing.Pool(args.nworkers) as pool:
        results = pool.map(run_one_structure, batch)

    failed = [sid for sid, ok in results if not ok]
    if failed:
        print(f"[FAILED] {len(failed)} structures: {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}")
        sys.exit(1)
    else:
        print(f"[DONE] all {len(sids)} structures completed successfully")


if __name__ == "__main__":
    main()
