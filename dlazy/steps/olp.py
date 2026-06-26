from pathlib import Path

from dpdispatcher import Task

from .. import config as dlazy_config
from .. import utils
from . import register_step


@register_step("olp")
class OLPStep:
    name: str = ""
    type: str = "olp"

    def __init__(self, defn, param, mcfg, ctx):
        self.defn = defn
        self.param = param
        self.mcfg = mcfg
        self.ctx = ctx
        self.name = defn["name"]

    def _get_software(self, key, default=None):
        return self.mcfg.get("openmx", {}).get(key, default)

    def prepare(self):
        tasks = []
        work_dir = Path(self.param["work_dir"])
        force = self.defn.get("force", False)

        executable = self._get_software("executable", "openmx")
        data_path = self._get_software("data_path")
        module_path = self._get_software("module_path")
        mpi_cmd_tmpl = self._get_software("mpi_cmd", "mpirun -np {cpus}")
        cpus = self._get_software("cpus_per_task", 64)

        Gen = dlazy_config.resolve_openmx_generator(module_path)
        gen = Gen(data_path=data_path) if Gen and data_path else None

        structures = utils.read_structures(self.param["structures"])

        for sid, poscar in structures:
            step_dir = work_dir / "restart" / self.name / sid
            step_dir.mkdir(parents=True, exist_ok=True)

            overlap_file = step_dir / "overlap.h5"
            if not force and overlap_file.exists():
                print(f"  skip (done): {sid}/{self.name}")
                continue

            if gen:
                gen.generate(str(poscar), output_dir=str(step_dir),
                             max_iter=1, scf_criterion=1e-3)
                print(f"  gen: {sid}/{self.name}")
            else:
                print(f"  WARNING: no generator for {sid}/{self.name}")
                continue

            dat_path = step_dir / "openmx_in.dat"
            if dat_path.exists():
                with open(dat_path, "a") as f:
                    f.write("\nscf.OverlapOnly     On\n")

            work_path = Path("restart") / self.name / sid
            tasks.append(Task(
                command=utils.make_mpi_cmd(mpi_cmd_tmpl, executable, cpus),
                task_work_path=str(work_path),
                forward_files=["openmx_in.dat"],
                backward_files=["overlap.h5", "info.json", "openmx.out", "openmx.std"],
                outlog="openmx.out",
            ))

        return tasks

    def collect(self):
        pass
