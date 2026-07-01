import json
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from dpdispatcher import Task


class MassiveMixin:
    """Massive-mode helpers used only when param.mode == 'massive'.

    Separated as a mixin so Step subclasses stay focused on step business
    logic; the mixin holds the manifest/runner-install machinery reused
    across all step types. Easy-mode code paths never touch these methods.
    """

    def _is_massive(self):
        return self.param.get("mode") == "massive"

    def _runner_script(self):
        """Path to the in-package runner script that gets forwarded to nodes."""
        return Path(__file__).resolve().parent.parent / "_runner.py"

    def _install_runner(self, work_dir):
        """Copy _runner.py into work_dir so dpdispatcher can forward it."""
        src = self._runner_script()
        dst = Path(work_dir) / "_runner.py"
        if not dst.exists() or dst.read_text() != src.read_text():
            shutil.copy2(src, dst)
        return "_runner.py"

    def _step_dir(self):
        return Path("restart") / self.name

    def build_manifest_tasks(self, sids, *, exe, mpi_cmd_tmpl, cpus,
                              forward_extra=None, backward_files=None,
                              outlog="runner.out"):
        """Build dpdispatcher Tasks in massive mode.

        Splits sids into batches of K (tasks_per_array from mcfg), writes
        a manifest per batch under restart/<step>/_manifest_<i>.json, and
        returns one Task per manifest. Each Task's command invokes
        _runner.py which handles node-local serial/parallel execution of
        its K sids.
        """
        work_dir = Path(self.param["work_dir"])
        runner_rel = self._install_runner(work_dir)
        step_cfg = self.mcfg.get(self.type_alias(), {})
        tasks_per_array = step_cfg.get("tasks_per_array", 5)
        runner_mode = step_cfg.get("runner_mode", self.runner_mode)
        if runner_mode == "single":
            runner_mode = "serial"
        nworkers = step_cfg.get("nworkers", tasks_per_array)

        step_dir = work_dir / "restart" / self.name
        status_dir = step_dir / "_status"
        status_dir.mkdir(parents=True, exist_ok=True)

        batches = [sids[i:i + tasks_per_array]
                   for i in range(0, len(sids), tasks_per_array)]

        tasks = []
        for batch_idx, batch_sids in enumerate(batches):
            manifest_name = f"_manifest_{batch_idx}.json"
            manifest_path = step_dir / manifest_name
            manifest_path.write_text(json.dumps({
                "step": self.name,
                "sids": batch_sids,
                "work_dir": str(work_dir.resolve()),
            }))

            cmd = (f"python3 {runner_rel} "
                   f"--manifest restart/{self.name}/{manifest_name} "
                   f"--exe {exe} --mpi '{mpi_cmd_tmpl}' "
                   f"--nprocs {cpus} --mode {runner_mode}")
            if runner_mode == "parallel":
                cmd += f" --nworkers {min(nworkers, len(batch_sids))}"

            forward = [runner_rel, f"restart/{self.name}/{manifest_name}"]
            if forward_extra:
                forward.extend(forward_extra)
            backward = list(backward_files) if backward_files else []

            tasks.append(Task(
                command=cmd,
                task_work_path=".",
                forward_files=forward,
                backward_files=backward,
                outlog=outlog,
            ))
        return tasks


class Step(MassiveMixin, ABC):
    """Base class for all workflow steps.

    Subclasses declare capabilities via class attributes:
        runner_mode: "serial" | "parallel" | "single"
            - "single"  : easy mode default, 1 task = 1 structure (legacy)
            - "serial"  : massive mode, 1 array element runs K structures sequentially
            - "parallel": massive mode, 1 array element runs K structures via Pool(K)
        produces_dataset: True if collect() yields DeepH training data
                          (engine exports these steps automatically)
        type_alias(): returns the mcfg section key for this step's software
                      config (default self.type; SCFStep overrides to 'fp').
    """

    name: str = ""
    type: str = ""
    runner_mode: str = "single"
    produces_dataset: bool = False

    def __init__(self, defn, param, mcfg, ctx):
        self.defn = defn
        self.param = param
        self.mcfg = mcfg
        self.ctx = ctx
        self.name = defn["name"]

    @abstractmethod
    def prepare(self):
        """Return list of dpdispatcher Task, or empty list if nothing to do.

        In easy mode (default): each Task typically wraps one structure.
        In massive mode: each Task wraps a manifest of K structures, run
        via dlazy/_runner.py on a single Slurm array element.
        """

    @abstractmethod
    def collect(self):
        """Post-process after all tasks finish. Update ctx."""

    def type_alias(self):
        """Return the mcfg section key for this step's software config.

        Default uses self.type. Subclasses can override (e.g. SCFStep
        uses 'fp' for historical compatibility).
        """
        return self.type