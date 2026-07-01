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
        if self.param.get("mode") == "massive":
            self.machine, self.resources, self.mcfg = config.load_machine_massive(machine_path)
        else:
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

    def _save_phase(self, step_name, phase):
        rec = self._load_record()
        rec[step_name] = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "structures_file": self.param["structures"],
            "structures_hash": self._structures_hash(),
            "phase": phase,
        }
        self._record_path.write_text(json.dumps(rec, indent=2) + "\n")

    def _get_phase(self, step_name):
        entry = self._load_record().get(step_name)
        if not entry or isinstance(entry, str):
            return None
        return entry.get("phase")

    def _step_is_done(self, step_name):
        entry = self._load_record().get(step_name)
        if not entry or isinstance(entry, str):
            return False
        if entry.get("structures_hash") != self._structures_hash():
            return False
        phase = entry.get("phase")
        return phase is None or phase == "02.collected"

    def collect_results(self, step_filter=None, all_sids=False):
        from .exporter import export_step_dataset, package_datasets
        from . import steps as step_mod
        rec = self._load_record()
        work_dir = Path(self.param["work_dir"])
        for defn in self.param.get("steps", []):
            sn = defn["name"]
            if step_filter and sn != step_filter:
                continue
            if sn not in rec:
                continue
            try:
                step_cls = step_mod._registry[defn.get("type")]
            except KeyError:
                continue
            if not getattr(step_cls, "produces_dataset", False):
                continue
            print(f"--- Export: {sn} ---")
            export_step_dataset(sn, structures_file=self.param["structures"],
                                work_dir=work_dir, discover_all=all_sids)
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

        if self.param.get("mode") == "massive":
            # Massive mode: work_dir is the shared filesystem; wf_runner
            # writes outputs there directly (no forward/backward copy in
            # LocalContext because forward/backward files are symlinks).
            # We only need to remove the staging tree, not move anything.
            shutil.rmtree(tmp_hash, ignore_errors=True)
            record.remove(sub.submission_hash)
            return

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

    def _aggregate_status(self, step_name):
        """Read restart/<step>/_status/_summary.ndjson and tally ok/fail.

        Returns dict {'total': N, 'ok': M, 'fail': K} or None if no status
        file exists yet.
        """
        summary = (Path(self.param["work_dir"]) / "restart" / step_name
                    / "_status" / "_summary.ndjson")
        if not summary.exists():
            return None
        ok = fail = 0
        seen = set()
        # Only the LAST state per sid counts (reruns may append twice).
        last_state = {}
        for line in summary.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = rec.get("sid")
            if not sid:
                continue
            last_state[sid] = rec.get("state")
        for state in last_state.values():
            if state == "ok":
                ok += 1
            else:
                fail += 1
        return {"total": len(last_state), "ok": ok, "fail": fail}

    def run(self, step_filter=None, dry_run=False,
             retry_failed=False, only_sids=None):
        name = self.param.get("name", "workflow")
        step_defs = self.param.get("steps", [])

        # Resolve sid filter: either explicit --only-sids or --retry-failed
        # reads aggregate_status from disk. Massive-mode only; in easy mode
        # these flags are silently ignored since prepare already skips done.
        sid_filter = None
        if only_sids:
            sid_filter = set(s.strip() for s in only_sids.split(",") if s.strip())
            print(f"[filter] only_sids: {len(sid_filter)} sids")
        elif retry_failed and self.param.get("mode") == "massive":
            # Try each step (filtered by --step if given) for failed sids
            if step_filter:
                stats = self._aggregate_status(step_filter)
                if stats is None:
                    print(f"[retry-failed] no _summary.ndjson for {step_filter}, "
                          f"running full step")
                else:
                    summary = (Path(self.param["work_dir"]) / "restart" / step_filter
                                / "_status" / "_summary.ndjson")
                    last_state = {}
                    for line in summary.read_text().splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        last_state[rec.get("sid")] = rec.get("state")
                    sid_filter = {sid for sid, st in last_state.items() if st != "ok"}
                    print(f"[retry-failed] {step_filter}: {len(sid_filter)} failed sids")
            else:
                print("[retry-failed] need --step to identify which step to retry")
                return
        if sid_filter is not None:
            self.ctx["_sid_filter"] = sid_filter

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

            phase = self._get_phase(defn["name"])
            step = steps.create_step(defn, self.param, self.mcfg, self.ctx)
            pfx = self.mcfg.get("job_name_prefix")
            label = f"{pfx}_{step.name}" if pfx else step.name
            print(f"--- Step {i+1}/{total_steps}: {step.name} (job: {label}) ---")

            tasks = step.prepare()
            if not tasks:
                print(f"  Nothing to do for {step.name}")
                step.collect()
                self._save_phase(step.name, "02.collected")
                continue

            print(f"  Tasks: {len(tasks)}")

            if dry_run:
                for t in tasks:
                    print(f"    [{t.task_work_path}] {t.command}")
                continue

            if phase is None:
                self._save_phase(step.name, "00.prepared")

            base = Path(self.param["_base"])
            self.machine.context.temp_remote_root = str(base / "tmp" / step.name)
            self.machine.context.temp_local_root = str(work_dir)

            self._set_job_name(step.name)

            # Apply per-step resource overrides from mcfg (by step.type_alias)
            step_cfg = self.mcfg.get(step.type_alias(), {})
            for key in ("cpus_per_task", "group_size"):
                if key in step_cfg:
                    old = getattr(self.resources, key, None)
                    setattr(self.resources, key, step_cfg[key])
                    print(f"  resource: {key} = {step_cfg[key]} (was {old})")

            # In massive mode, group_size default = total tasks so all
            # manifest Tasks go into a single sbatch (--array=0-N).
            # SlurmJobArray was loaded in Workflow.__init__; its
            # resources.kwargs.slurm_job_size=1 makes each Task (each
            # manifest of K sids) one array element.
            # TODO: support massive.max_array_parallel via patching the
            # generated --array line with `%N' throttle suffix; for now
            # the scheduler queues all array elements naturally.
            if self.param.get("mode") == "massive":
                if not tasks:
                    self.resources.group_size = 1
                elif "group_size" not in step_cfg:
                    self.resources.group_size = len(tasks)

            sub = Submission(
                work_base=".",
                machine=self.machine,
                resources=self.resources,
                task_list=tasks,
            )

            if phase in (None, "00.prepared"):
                sub.generate_jobs()
                sub.update_submission_state()

                if not sub.check_all_finished():
                    sub.upload_jobs()
                    sub.handle_unexpected_submission_state()
                    self._save_phase(step.name, "01.submitted")
                    sub.submission_to_json()
                    time.sleep(1)
                    sub.update_submission_state()
                    sub.check_all_finished()
                    sub.handle_unexpected_submission_state()

            elif phase == "01.submitted":
                sub.try_recover_from_json()
                sub.update_submission_state()
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
                if self.param.get("mode") == "massive":
                    stats = self._aggregate_status(step.name)
                    if stats:
                        line += f"  | ok:{stats['ok']} fail:{stats['fail']}/{stats['total']}"
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
            self._save_phase(step.name, "02.collected")

            if self.param.get("mode") == "massive":
                stats = self._aggregate_status(step.name)
                if stats:
                    print(f"  [{step.name}] final: ok={stats['ok']}/{stats['total']} "
                          f"fail={stats['fail']}")

            if step.produces_dataset:
                from .exporter import export_step_dataset
                export_step_dataset(step.name,
                    structures_file=self.param["structures"],
                    work_dir=work_dir)

        if not step_filter and not dry_run:
            from .exporter import package_datasets
            package_datasets(work_dir)

        print()
        print("========== Done ==========")
