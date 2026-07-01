from pathlib import Path

from dpdispatcher import Task

from .. import config as dlazy_config
from .. import utils
from . import register_step
from .base import Step


@register_step("scf")
class SCFStep(Step):
    type: str = "scf"
    runner_mode: str = "serial"
    produces_dataset: bool = True

    def _get_openmx(self, key, default=None):
        return self.defn.get(key, self.param.get("openmx", {}).get(key, default))

    def _get_software(self, key, default=None):
        return self.mcfg.get("fp", {}).get(key, default)

    def _get_deeph(self, key, default=None):
        return self.mcfg.get("deeph", {}).get(key, default)

    def type_alias(self):
        return "fp"

    def _resolve_deeph_dir(self):
        ctx_dir = self.ctx.get("_deeph_dir")
        if ctx_dir:
            return ctx_dir

        candidates = []

        for s in self.param.get("steps", []):
            if s.get("type") in ("deeph",) and s.get("deeph_dir"):
                d = str((Path(self.param["_base"]) / s["deeph_dir"]).resolve())
                candidates.append(d)

        outputs_base = Path(self.param["work_dir"]) / "inference" / "outputs"
        candidates.append(str(outputs_base))
        return dlazy_config.find_latest_deeph_dir(candidates)

    def _find_prev_hamiltonian(self, work_dir, sid):
        """Find the latest hamiltonian from a previous SCF-type step in param order.

        Uses param.json `steps` ordering (not lexicographic step name) so
        e10/e2-style names are handled correctly.
        """
        restart = Path(work_dir) / "restart"
        if not restart.is_dir():
            return None
        prev_name = None
        for s in self.param.get("steps", []):
            if s.get("name") == self.name:
                break
            if s.get("type") in ("scf", "scf-restart"):
                prev_name = s.get("name")
        if not prev_name:
            return None
        h = utils.find_final_hamiltonian(restart / prev_name / sid)
        return h

    def _prepare_one(self, args):
        """Worker fn for multiprocessing: generate openmx_in.dat for one sid.

        Returns (sid, gen_ok). Side effect: writes openmx_in.dat to step_dir.
        """
        sid, poscar, work_dir, gen, openmx_defaults, init_source, \
            deeph_dir, prev_results, check_pred = args

        step_dir = Path(work_dir) / "restart" / self.name / sid
        step_dir.mkdir(parents=True, exist_ok=True)
        pred_link = step_dir / "hamiltonian_pred.h5"
        inp_path = step_dir / "openmx_in.dat"
        std_path = step_dir / "openmx.std"

        # In easy mode, skip already-finished sids.
        # In massive mode, never skip here - wf_runner handles skip per-sid
        # at execution time so the submission_hash stays stable.
        if not self._is_massive() and utils.check_finished(std_path):
            stale = False
            if init_source == "deeph" and pred_link.is_symlink() and std_path.exists():
                stale = pred_link.lstat().st_mtime_ns > std_path.stat().st_mtime_ns
            if not stale:
                return sid, "skip"

        if not inp_path.exists():
            if gen:
                gen.generate(str(poscar), output_dir=str(step_dir),
                             max_iter=self._get_openmx("max_iter", 200),
                             mixing_type=self._get_openmx("mixing_type", "RMM-DIISH"),
                             scf_criterion=self._get_openmx("scf_criterion", 1e-6),
                             startpulay=self._get_openmx("startpulay",
                                                          openmx_defaults.get("startpulay", 3)),
                             mixing_history=self._get_openmx("mixing_history",
                                                              openmx_defaults.get("mixing_history", 30)),
                             init_mixing_weight=openmx_defaults.get("init_mixing_weight", 0.3),
                             max_mixing_weight=openmx_defaults.get("max_mixing_weight", 0.8),
                             detailed_output=openmx_defaults.get("detailed_output", False),
                             step1_mix_h=openmx_defaults.get("step1_mix_h", False),
                             step_output=self._get_openmx("step_output"))
                if inp_path.exists() and "scf.OverlapOnly" not in inp_path.read_text():
                    with open(inp_path, "a") as f:
                        f.write("scf.OverlapOnly     Off\n")
                return sid, "gen"
            return sid, "nogen"

        # Link hamiltonian_pred.h5 from deeph or prev step
        if init_source == "none":
            return sid, "skip_link"
        elif init_source == "deeph":
            if not deeph_dir:
                if check_pred:
                    return sid, "err_deeph_dir"
                return sid, "skip_link"
            src = (Path(deeph_dir) / sid / "hamiltonian_pred.h5").resolve()
            if not src.exists():
                if check_pred:
                    return sid, f"err_deeph_file:{src}"
                return sid, "skip_link"
            if pred_link.is_symlink() or pred_link.exists():
                pred_link.unlink()
            pred_link.symlink_to(src)
            return sid, "link"
        elif init_source == "prev":
            src_path = None
            if prev_results:
                src_path = prev_results.get(sid)
            if not src_path or not Path(src_path).exists():
                src_path = self._find_prev_hamiltonian(work_dir, sid)
            if src_path and Path(src_path).exists():
                if pred_link.is_symlink() or pred_link.exists():
                    pred_link.unlink()
                pred_link.symlink_to(Path(src_path).resolve())
                return sid, "link"
            return sid, "skip_link"
        return sid, "skip_link"

    def _prepare(self, check_pred):
        work_dir = Path(self.param["work_dir"])
        openmx_defaults = self.param.get("openmx", {})

        executable = self._get_software("executable", "openmx")
        mpi_cmd_tmpl = self._get_software("mpi_cmd", "mpirun -np {cpus}")
        cpus = self._get_software("cpus_per_task", 64)

        Gen = dlazy_config.resolve_openmx_generator()
        data_path = self._get_software("data_path")
        gen = Gen(data_path=data_path) if Gen and data_path else None

        structures = utils.read_structures(self.param["structures"])
        prev_results = self.ctx.get("_final_h")
        init_source = self.defn.get("init_from", "deeph")
        deeph_dir = self._resolve_deeph_dir() if init_source == "deeph" else None

        args_list = [(sid, poscar, work_dir, gen, openmx_defaults,
                      init_source, deeph_dir, prev_results, check_pred)
                     for sid, poscar in structures]

        # Generate inputs: parallel in massive mode, serial in easy mode.
        # multiprocessing is safe here because gen.generate is CPU-bound
        # jinja2 rendering and does not mutate shared state.
        results = []
        if self._is_massive() and gen and len(args_list) > 1:
            import multiprocessing
            nproc = min(8, multiprocessing.cpu_count(), len(args_list))
            with multiprocessing.Pool(nproc) as pool:
                results = pool.map(self._prepare_one, args_list)
        else:
            for a in args_list:
                results.append(self._prepare_one(a))

        # Tally and print progress
        counts = {}
        for sid, status in results:
            counts[status] = counts.get(status, 0) + 1
        total = len(structures)
        utils.print_progress_bar(total, total, self.name)
        parts = [f"{v} {k}" for k, v in counts.items() if v]
        if parts:
            print(f"  [{self.name}] " + ", ".join(parts))

        # Surface errors regardless of mode
        for sid, status in results:
            if status.startswith("err_"):
                if "dir" in status:
                    print(f"  ERROR: no inference dir, cannot init {sid}/{self.name}")
                else:
                    print(f"  ERROR: {status.split(':', 1)[-1]} not found for {sid}/{self.name}")
            elif status == "nogen":
                print(f"  WARNING: no generator for {sid}/{self.name}")

        # Build dpdispatcher Tasks
        # easy mode: 1 Task per structure (legacy). Skip sids that were
        #   already finished (status == 'skip') so we don't resubmit them.
        # massive mode: 1 Task per K-sid manifest via build_manifest_tasks.
        #   Include all sids (even 'skip') so submission_hash is stable
        #   across re-runs; wf_runner skips ok sids at execution time.
        if self._is_massive():
            all_sids = [sid for sid, _ in structures]
            if not all_sids:
                return []
            return self.build_manifest_tasks(
                all_sids,
                exe=executable,
                mpi_cmd_tmpl=mpi_cmd_tmpl,
                cpus=cpus,
                forward_extra=[f"restart/{self.name}/*/openmx_in.dat",
                                f"restart/{self.name}/*/hamiltonian_pred.h5"],
                backward_files=[f"restart/{self.name}/*/openmx.std",
                                f"restart/{self.name}/*/hamiltonians_step*.h5"],
                outlog="openmx.out",
            )

        # easy mode: per-structure Task
        tasks = []
        for (sid, _), (_, status) in zip(structures, results):
            if status == "skip":
                continue
            step_dir = work_dir / "restart" / self.name / sid
            pred_link = step_dir / "hamiltonian_pred.h5"
            work_path = Path("restart") / self.name / sid
            forward = ["openmx_in.dat"]
            if pred_link.is_symlink() or pred_link.exists():
                forward.append("hamiltonian_pred.h5")
            tasks.append(Task(
                command=utils.make_mpi_cmd(mpi_cmd_tmpl, executable, cpus),
                task_work_path=str(work_path),
                forward_files=forward,
                backward_files=["openmx.std", "hamiltonians_step*.h5"],
                outlog="openmx.out",
            ))
        return tasks

    def prepare(self):
        return self._prepare(check_pred=False)

    def collect(self):
        work_dir = Path(self.param["work_dir"])
        structures = utils.read_structures(self.param["structures"])
        final_h = {}
        for sid, _ in structures:
            step_dir = work_dir / "restart" / self.name / sid
            h = utils.find_final_hamiltonian(step_dir)
            if h:
                final_h[sid] = h
        self.ctx["_final_h"] = final_h
        self.ctx[f"_final_h_{self.name}"] = final_h
        utils.print_progress_bar(len(final_h), len(structures), self.name)


@register_step("scf-restart")
class SCFRestartStep(SCFStep):
    runner_mode: str = "serial"
    produces_dataset: bool = True
    def prepare(self):
        return self._prepare(check_pred=True)
