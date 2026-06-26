import json
import shutil
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

        olp_cfg = self.mcfg.get("olp", {})
        nprocs = olp_cfg.get("nprocs", 8)
        nworkers = olp_cfg.get("nworkers", 7)

        Gen = dlazy_config.resolve_openmx_generator(module_path)
        gen = Gen(data_path=data_path) if Gen and data_path else None

        structures = utils.read_structures(self.param["structures"])

        # Generation pass: create openmx_in.dat for all pending structures
        pending = []
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

            pending.append(sid)

        if not pending:
            print(f"  Nothing to do for {self.name}")
            return []

        # Copy parallel worker script to work_dir
        script_src = Path(__file__).parent / "_olp_parallel.py"
        script_dst = work_dir / "_olp_parallel.py"
        shutil.copy2(script_src, script_dst)

        # Split pending into batches of nworkers
        batches = [pending[i:i + nworkers] for i in range(0, len(pending), nworkers)]
        print(f"  nworkers={nworkers}, nprocs={nprocs}, {len(batches)} batch(es), {len(pending)} structures")

        for batch_idx, sids in enumerate(batches):
            manifest_name = f"_olp_manifest_{batch_idx}.json"
            manifest_path = work_dir / "restart" / self.name / manifest_name
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps({
                "work_dir": str(work_dir.resolve()),
                "sids": sids
            }))

            tasks.append(Task(
                command=f"python3 _olp_parallel.py --manifest restart/{self.name}/{manifest_name} "
                        f"--exe {executable} --mpi '{mpi_cmd_tmpl}' "
                        f"--nprocs {nprocs} --nworkers {min(nworkers, len(sids))}",
                task_work_path=".",
                forward_files=["_olp_parallel.py", f"restart/{self.name}/{manifest_name}"],
                backward_files=[f"restart/{self.name}/*/overlap.h5",
                                f"restart/{self.name}/*/info.json",
                                f"restart/{self.name}/*/openmx.out",
                                f"restart/{self.name}/*/openmx.std",
                                f"restart/{self.name}/_olp_manifest_*.json"],
                outlog="_olp_parallel.out",
            ))

        return tasks

    def collect(self):
        work_dir = Path(self.param["work_dir"])
        structures = utils.read_structures(self.param["structures"])
        done = sum(1 for sid, _ in structures
                   if (work_dir / "restart" / self.name / sid / "overlap.h5").exists())
        utils.print_progress_bar(done, len(structures), self.name)
