from pathlib import Path

from dpdispatcher import Task

from .. import config as dlazy_config
from .. import utils
from . import register_step


@register_step("scf")
class SCFStep:
    name: str = ""
    type: str = "scf"

    def __init__(self, defn, param, mcfg, ctx):
        self.defn = defn
        self.param = param
        self.mcfg = mcfg
        self.ctx = ctx
        self.name = defn["name"]

    def _get_openmx(self, key, default=None):
        return self.defn.get(key, self.param.get("openmx", {}).get(key, default))

    def _get_software(self, key, default=None):
        return self.mcfg.get("fp", {}).get(key, default)

    def _get_deeph(self, key, default=None):
        return self.mcfg.get("deeph", {}).get(key, default)

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
        restart = Path(work_dir) / "restart"
        if not restart.is_dir():
            return None
        prev_dirs = sorted(d for d in restart.iterdir() if d.is_dir() and d.name < self.name)
        if not prev_dirs:
            return None
        h = utils.find_final_hamiltonian(prev_dirs[-1] / sid)
        return h

    def _prepare(self, check_pred):
        tasks = []
        work_dir = Path(self.param["work_dir"])
        openmx_defaults = self.param.get("openmx", {})

        executable = self._get_software("executable", "openmx")
        data_path = self._get_software("data_path")
        mpi_cmd_tmpl = self._get_software("mpi_cmd", "mpirun -np {cpus}")
        cpus = self._get_software("cpus_per_task", 64)

        Gen = dlazy_config.resolve_openmx_generator()
        gen = Gen(data_path=data_path) if Gen and data_path else None

        structures = utils.read_structures(self.param["structures"])
        prev_results = self.ctx.get("_final_h")

        total = len(structures)
        done = 0
        n_gen = 0
        n_link = 0
        n_skip = 0

        for sid, poscar in structures:
            done += 1
            step_dir = work_dir / "restart" / self.name / sid
            step_dir.mkdir(parents=True, exist_ok=True)

            pred_link = step_dir / "hamiltonian_pred.h5"
            init_source = self.defn.get("init_from", "deeph")

            std_path = step_dir / "openmx.std"
            if utils.check_finished(std_path):
                stale = False
                if init_source == "deeph" and pred_link.is_symlink() and std_path.exists():
                    stale = pred_link.lstat().st_mtime_ns > std_path.stat().st_mtime_ns
                if not stale:
                    n_skip += 1
                    utils.update_progress(done, total, self.name)
                    continue

            inp_path = step_dir / "openmx_in.dat"
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
                                 detailed_output=openmx_defaults.get("detailed_output", True),
                                 step1_mix_h=openmx_defaults.get("step1_mix_h", False))
                    if inp_path.exists() and "scf.OverlapOnly" not in inp_path.read_text():
                        with open(inp_path, "a") as f:
                            f.write("scf.OverlapOnly     Off\n")
                    n_gen += 1
                else:
                    print(f"\n  WARNING: no generator for {sid}/{self.name}")

            if init_source == "none":
                pass
            elif init_source == "deeph":
                deeph_dir = self._resolve_deeph_dir()
                if not deeph_dir:
                    if check_pred:
                        print(f"\n  ERROR: no inference output dir, cannot initialize {sid}/{self.name}")
                        continue
                    print(f"\n  WARNING: no inference output dir for {sid}/{self.name}, cold-start SCF")
                else:
                    src = (Path(deeph_dir) / sid / "hamiltonian_pred.h5").resolve()
                    if not src.exists():
                        if check_pred:
                            print(f"\n  ERROR: {src} not found, cannot initialize {sid}/{self.name}")
                            continue
                        print(f"\n  WARNING: {src} not found for {sid}/{self.name}, cold-start SCF")
                    else:
                        if pred_link.is_symlink() or pred_link.exists():
                            pred_link.unlink()
                        pred_link.symlink_to(src)
                        n_link += 1

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
                    n_link += 1

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

            utils.update_progress(done, total, self.name)

        print()
        if n_gen or n_link or n_skip:
            print(f"  [{self.name}] {n_gen} gen, {n_link} link, {n_skip} skip")

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
    def prepare(self):
        return self._prepare(check_pred=True)
