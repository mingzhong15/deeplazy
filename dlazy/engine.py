import hashlib
import json
import shutil
import time
from pathlib import Path

from dpdispatcher import Submission
from dpdispatcher.utils.record import record

from . import config, steps


class Workflow:
    def __init__(self, param_path, machine_path):
        self.param = config.load_param(param_path)
        self.machine, self.resources, self.mcfg = config.load_machine(machine_path)
        self.ctx = {}

        base = Path(self.param["_base"])
        record.record_directory = base / ".dpdispatcher" / "submission"
        record.record_directory.mkdir(parents=True, exist_ok=True)

        self._record_path = base / "record.dlazy"

    def _load_record(self):
        if self._record_path.exists():
            return json.loads(self._record_path.read_text())
        return {}

    def _structures_hash(self):
        p = self._resolve_structures_path()
        if not p or not p.exists():
            return None
        return hashlib.md5(p.read_bytes()).hexdigest()[:12]

    def _resolve_structures_path(self):
        raw = self.param.get("structures")
        if not raw:
            return None
        p = Path(raw)
        if p.is_absolute():
            return p
        return Path(self.param["_base"]) / p

    def _save_record(self, step_name):
        rec = self._load_record()
        rec[step_name] = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "structures_file": self.param["structures"],
            "structures_hash": self._structures_hash(),
        }
        self._record_path.write_text(json.dumps(rec, indent=2) + "\n")

    def _step_is_done(self, step_name):
        entry = self._load_record().get(step_name)
        if not entry:
            return False
        if isinstance(entry, str):
            return False
        if entry.get("structures_hash") != self._structures_hash():
            return False
        return True

    def collect_results(self, step_filter=None):
        from .exporter import export_step_dataset, package_datasets
        rec = self._load_record()
        work_dir = Path(self.param["work_dir"])
        for defn in self.param.get("steps", []):
            sn = defn["name"]
            if step_filter and sn != step_filter:
                continue
            if sn not in rec:
                continue
            if defn.get("type") not in ("scf", "scf-restart"):
                continue
            print(f"--- Export: {sn} ---")
            export_step_dataset(sn, structures_file=self.param["structures"],
                                work_dir=work_dir)
        package_datasets(work_dir)

    def _set_job_name(self, step_name):
        prefix = self.mcfg.get("job_name_prefix")
        if not prefix:
            return
        job_name = f"{prefix}_{step_name}"
        flags = list(self.resources.custom_flags) if self.resources.custom_flags else []
        flags = [f for f in flags if not f.startswith("#SBATCH --job-name=")]
        flags.append(f"#SBATCH --job-name={job_name}")
        self.resources.custom_flags = flags

    def _cleanup_step(self, sub, step_name=None):
        base = Path(self.param["_base"])
        work_dir = Path(self.param["work_dir"])
        tmp_hash = base / "tmp" / step_name / sub.submission_hash if step_name else base / "tmp" / sub.submission_hash
        patterns = self.mcfg.get(step_name, {}).get("backward_files") if step_name else None

        if tmp_hash.is_dir():
            for std in tmp_hash.rglob("openmx.std"):
                task_dir = std.parent
                rel = task_dir.relative_to(tmp_hash)
                dst = work_dir / rel
                dst.mkdir(parents=True, exist_ok=True)

                if patterns:
                    for pat in patterns:
                        for f in task_dir.glob(pat):
                            shutil.move(str(f), str(dst / f.name))
                else:
                    for f in task_dir.iterdir():
                        if f.name == "openmx.std":
                            continue
                        if f.name in ("openmx_in.dat", "hamiltonian_pred.h5"):
                            continue
                        shutil.move(str(f), str(dst / f.name))
            shutil.rmtree(tmp_hash, ignore_errors=True)

        record.remove(sub.submission_hash)

    def run(self, step_filter=None, dry_run=False):
        name = self.param.get("name", "workflow")
        step_defs = self.param.get("steps", [])

        print(f"========== dlazy: {name} ==========")
        print(f"Work dir: {self.param.get('work_dir', '?')}")
        total_steps = len(step_defs)
        print(f"Steps:    {total_steps}")
        gs = self.resources.group_size
        if gs:
            print(f"Group:    {gs} tasks/job")
        print()

        work_dir = Path(self.param["work_dir"])

        for i, defn in enumerate(step_defs):
            if step_filter and defn["name"] != step_filter:
                continue
            if not step_filter and self._step_is_done(defn["name"]):
                print(f"  skip (already done): {defn['name']}")
                continue

            step = steps.create_step(defn, self.param, self.mcfg, self.ctx)
            pfx = self.mcfg.get("job_name_prefix")
            label = f"{pfx}_{step.name}" if pfx else step.name
            print(f"--- Step {i+1}/{total_steps}: {step.name} (job: {label}) ---")

            tasks = step.prepare()
            if not tasks:
                print(f"  Nothing to do for {step.name}")
                step.collect()
                self._save_record(step.name)
                continue

            print(f"  Tasks: {len(tasks)}")

            if dry_run:
                for t in tasks:
                    print(f"    [{t.task_work_path}] {t.command}")
                continue

            base = Path(self.param["_base"])
            self.machine.context.temp_remote_root = str(base / "tmp" / step.name)
            self.machine.context.temp_local_root = str(work_dir)

            self._set_job_name(step.name)

            # Apply per-step resource overrides from mcfg
            step_type = defn.get("type")
            step_cfg = self.mcfg.get(step_type, {})
            for key in ("cpus_per_task", "group_size"):
                if key in step_cfg:
                    old = getattr(self.resources, key, None)
                    setattr(self.resources, key, step_cfg[key])
                    print(f"  resource: {key} = {step_cfg[key]} (was {old})")

            sub = Submission(
                work_base=".",
                machine=self.machine,
                resources=self.resources,
                task_list=tasks,
            )

            sub.generate_jobs()
            sub.try_recover_from_json()
            sub.update_submission_state()

            if not sub.check_all_finished():
                sub.upload_jobs()
                sub.handle_unexpected_submission_state()
                sub.submission_to_json()
                time.sleep(1)
                sub.update_submission_state()
                sub.check_all_finished()
                sub.handle_unexpected_submission_state()

            total_jobs = len(sub.belonging_jobs)
            check_interval = 30
            ratio_unfinished = sub.resources.strategy.get("ratio_unfinished", 0.0)
            t0 = time.time()

            while not sub.check_all_finished():
                if ratio_unfinished > 0.0 and sub.check_ratio_unfinished(ratio_unfinished):
                    sub.remove_unfinished_tasks()
                    break

                time.sleep(check_interval)
                sub.update_submission_state()
                sub.handle_unexpected_submission_state()

                states = {}
                for job in sub.belonging_jobs:
                    s = job.job_state.name if hasattr(job.job_state, 'name') else str(job.job_state)
                    states[s] = states.get(s, 0) + 1

                elapsed = int(time.time() - t0)
                parts = [f"{s}:{c}" for s, c in sorted(states.items())]
                line = f"\r  [elapsed {elapsed // 60:>2}m {elapsed % 60:>2}s]  {'  '.join(parts)}"
                print(f"{line:<70}", end="", flush=True)

            print()
            sub.handle_unexpected_submission_state()
            try:
                sub.try_download_result()
            except FileNotFoundError:
                print(f"  WARNING: some .h5 missing (SCF not converged for some structures)")
            sub.submission_to_json()
            sub.clean_jobs()

            self._cleanup_step(sub, step.name)
            step.collect()
            self._save_record(step.name)

            if defn.get("type") in ("scf", "scf-restart"):
                from .exporter import export_step_dataset
                export_step_dataset(step.name,
                    structures_file=self.param["structures"],
                    work_dir=work_dir)

        if not step_filter and not dry_run:
            from .exporter import package_datasets
            package_datasets(work_dir)

        print()
        print("========== Done ==========")
