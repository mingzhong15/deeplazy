import json
from dataclasses import dataclass
from pathlib import Path

from dpdispatcher import Task

from .. import config as dlazy_config
from .. import utils
from . import register_step
from .base import Step


@dataclass
class OlpInput:
    """One OLP structure's input preparation context."""
    sid: str
    poscar: str
    work_dir: Path
    gen: object        # OpenMXGenerator | None
    force: bool


@register_step("olp")
class OLPStep(Step):
    type: str = "olp"
    runner_mode: str = "parallel"
    produces_dataset: bool = False

    def _get_software(self, key, default=None):
        return self.mcfg.get("olp", {}).get(key, default)

    def type_alias(self):
        return "olp"

    def _generate_one(self, inp: OlpInput):
        """Worker fn for one OLP structure: generate openmx_in.dat with OverlapOnly.

        Returns (sid, status). status: 'gen' | 'skip' | 'nogen'.
        """
        step_dir = Path(inp.work_dir) / "restart" / self.name / inp.sid
        step_dir.mkdir(parents=True, exist_ok=True)
        overlap_file = step_dir / "overlap.h5"

        if not inp.force and overlap_file.exists():
            return inp.sid, "skip"

        if not inp.gen:
            return inp.sid, "nogen"

        inp.gen.generate(str(inp.poscar), output_dir=str(step_dir),
                     max_iter=1, scf_criterion=1e-3)
        dat_path = step_dir / "openmx_in.dat"
        if dat_path.exists():
            with open(dat_path, "a") as f:
                f.write("\nscf.OverlapOnly     On\n")
        return inp.sid, "gen"

    def prepare(self):
        work_dir = Path(self.param["work_dir"])
        force = self.defn.get("force", False)

        executable = self._get_software("executable", "openmx")
        mpi_cmd_tmpl = self._get_software("mpi_cmd", "mpirun -np {cpus}")
        nprocs = self._get_software("nprocs", 8)

        Gen = dlazy_config.resolve_openmx_generator()
        data_path = self._get_software("data_path")
        gen = Gen(data_path=data_path) if Gen and data_path else None

        structures = utils.read_structures(self.param["structures"])
        sid_filter = self.ctx.get("_sid_filter")
        if sid_filter is not None:
            structures = [(sid, p) for sid, p in structures if sid in sid_filter]
            print(f"  [{self.name}] sid filter: {len(structures)} of {len(sid_filter)} requested")
        inputs = [OlpInput(sid=sid, poscar=poscar, work_dir=work_dir,
                            gen=gen, force=force) for sid, poscar in structures]

        # Generate inputs in parallel in massive mode (or serial in easy mode)
        if self._is_massive() and gen and len(inputs) > 1:
            import multiprocessing
            nproc = min(8, multiprocessing.cpu_count(), len(inputs))
            with multiprocessing.Pool(nproc) as pool:
                results = pool.map(self._generate_one, inputs)
        else:
            results = [self._generate_one(i) for i in inputs]

        counts = {}
        for sid, status in results:
            counts[status] = counts.get(status, 0) + 1
        utils.print_progress_bar(len(structures), len(structures), self.name)
        parts = [f"{v} {k}" for k, v in counts.items() if v]
        if parts:
            print(f"  [{self.name}] " + ", ".join(parts))
        for sid, status in results:
            if status == "nogen":
                print(f"  WARNING: no generator for {sid}/{self.name}")

        # In easy mode, OLP already used a parallel runner (_olp_parallel.py).
        # In massive mode, use the unified _runner.py with --mode parallel.
        # Both split pending sids into batches of nworkers.
        pending = [sid for sid, status in results if status == "gen"]
        if not pending:
            return []

        if self._is_massive():
            return self.build_manifest_tasks(
                pending,
                exe=executable,
                mpi_cmd_tmpl=mpi_cmd_tmpl,
                cpus=nprocs,
                forward_extra=[f"restart/{self.name}/*/openmx_in.dat"],
                backward_files=[f"restart/{self.name}/*/overlap.h5",
                                f"restart/{self.name}/*/info.json",
                                f"restart/{self.name}/*/openmx.std",
                                f"restart/{self.name}/_manifest_*.json"],
                outlog="olp_runner.out",
            )

        # easy mode: keep legacy _olp_parallel.py batching
        nworkers = self._get_software("nworkers", 7)
        import shutil
        script_src = Path(__file__).parent / "_olp_parallel.py"
        script_dst = work_dir / "_olp_parallel.py"
        shutil.copy2(script_src, script_dst)

        batches = [pending[i:i + nworkers] for i in range(0, len(pending), nworkers)]
        print(f"  nworkers={nworkers}, nprocs={nprocs}, "
              f"{len(batches)} batch(es), {len(pending)} structures")

        tasks = []
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
