import shutil
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

        for i, defn in enumerate(step_defs):
            if step_filter and defn["name"] != step_filter:
                continue

            step = steps.create_step(defn, self.param, self.mcfg, self.ctx)
            pfx = self.mcfg.get("job_name_prefix")
            label = f"{pfx}_{step.name}" if pfx else step.name
            print(f"--- Step {i+1}/{total_steps}: {step.name} (job: {label}) ---")

            tasks = step.prepare()
            if not tasks:
                print(f"  Nothing to do for {step.name}")
                step.collect()
                continue

            print(f"  Tasks: {len(tasks)}")

            if dry_run:
                for t in tasks:
                    print(f"    [{t.task_work_path}] {t.command}")
                continue

            base = Path(self.param["_base"])
            work_dir = Path(self.param["work_dir"])
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
            try:
                sub.run_submission()
            except FileNotFoundError:
                print(f"  WARNING: some .h5 missing (SCF not converged for some structures)")
            self._cleanup_step(sub, step.name)
            step.collect()

        print()
        print("========== Done ==========")
