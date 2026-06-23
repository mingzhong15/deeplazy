from pathlib import Path

from dpdispatcher import Task

from .. import utils
from . import register_step
from ..config import resolve_openmx_generator


@register_step("scf")
class RestartSCFStep:
    name: str = ""
    type: str = "scf"

    def __init__(self, defn, param, ctx):
        self.defn = defn
        self.param = param
        self.ctx = ctx
        self.name = defn["name"]

    def prepare(self):
        tasks = []
        structures = utils.read_structures(
            self.param["structures"],
            base=self.param.get("structures_base"),
        )
        openmx_cfg = self.param.get("openmx", {})
        exe = openmx_cfg["executable"]
        work_dir = Path(self.param["work_dir"])
        calc_type = openmx_cfg.get("calc_type", "restart")
        cpus = self.param.get("cpus_per_task", 64)
        mpi_cmd_tmpl = self.param.get("mpi_cmd", "mpirun -np {cpus}")

        Gen = resolve_openmx_generator(self.param)
        gen = Gen(data_path=openmx_cfg["data_path"]) if Gen else None

        prev_results = self.ctx.get("_final_h")

        for sid, poscar in structures:
            step_dir = work_dir / calc_type / sid / self.name
            step_dir.mkdir(parents=True, exist_ok=True)

            std_path = step_dir / "openmx.std"
            if utils.check_finished(std_path):
                print(f"  skip (done): {sid}/{self.name}")
                continue

            inp = step_dir / "openmx_in.dat"
            if not inp.exists():
                if gen:
                    gen.generate(str(poscar), output_dir=str(step_dir),
                                 max_iter=openmx_cfg.get("max_iter", 200),
                                 mixing_type=openmx_cfg.get("mixing_type", "RMM-DIISH"),
                                 scf_criterion=self.defn.get("scf_criterion", 1e-6),
                                 startpulay=self.defn.get("startpulay",
                                                           openmx_cfg.get("startpulay", 3)),
                                 mixing_history=self.defn.get("mixing_history",
                                                              openmx_cfg.get("mixing_history", 30)),
                                 init_mixing_weight=openmx_cfg.get("init_mixing_weight", 0.3),
                                 max_mixing_weight=openmx_cfg.get("max_mixing_weight", 0.8),
                                 detailed_output=openmx_cfg.get("detailed_output", True),
                                 step1_mix_h=openmx_cfg.get("step1_mix_h", False))
                    print(f"  gen: {sid}/{self.name}")
                else:
                    print(f"  WARNING: no generator for {sid}/{self.name}, must create openmx_in.dat manually")

            init_source = self.defn.get("init_from", "deeph")
            pred_link = step_dir / "hamiltonian_pred.h5"

            if init_source == "deeph":
                deeph_dir = openmx_cfg.get("deeph_dir")
                if deeph_dir:
                    src = Path(deeph_dir) / sid / "hamiltonian_pred.h5"
                    if src.exists():
                        if pred_link.is_symlink() or pred_link.exists():
                            pred_link.unlink()
                        pred_link.symlink_to(src)
                        print(f"  link deeph: {sid}/{self.name}")

            elif init_source == "prev" and prev_results:
                src_path = prev_results.get(sid)
                if src_path and Path(src_path).exists():
                    if pred_link.is_symlink() or pred_link.exists():
                        pred_link.unlink()
                    pred_link.symlink_to(Path(src_path))
                    print(f"  link prev: {sid}/{self.name}")

            rel_path = step_dir.relative_to(work_dir)
            tasks.append(Task(
                command=utils.make_mpi_cmd(mpi_cmd_tmpl, exe, cpus),
                task_work_path=str(rel_path),
                forward_files=["openmx_in.dat"],
                backward_files=["openmx.std", "hamiltonians_step*.h5"],
                outlog="openmx.out",
            ))

        return tasks

    def collect(self):
        structures = utils.read_structures(
            self.param["structures"],
            base=self.param.get("structures_base"),
        )
        work_dir = Path(self.param["work_dir"])
        calc_type = self.param.get("openmx", {}).get("calc_type", "restart")
        final_h = {}
        for sid, _ in structures:
            step_dir = work_dir / calc_type / sid / self.name
            h = utils.find_final_hamiltonian(step_dir)
            if h:
                final_h[sid] = h
        self.ctx["_final_h"] = final_h
        self.ctx[f"_final_h_{self.name}"] = final_h
