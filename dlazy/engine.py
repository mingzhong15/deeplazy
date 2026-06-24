from dpdispatcher import Submission

from . import config, steps


class Workflow:
    def __init__(self, param_path, machine_path):
        self.param = config.load_param(param_path)
        self.machine, self.resources, self.mcfg = config.load_machine(machine_path)
        self.ctx = {}

    def _set_job_name(self, step_name):
        prefix = self.mcfg.get("job_name_prefix")
        if not prefix:
            return
        job_name = f"{prefix}_{step_name}"
        flags = list(self.resources.custom_flags) if self.resources.custom_flags else []
        flags = [f for f in flags if not f.startswith("#SBATCH --job-name=")]
        flags.append(f"#SBATCH --job-name={job_name}")
        self.resources.custom_flags = flags

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

            self._set_job_name(step.name)
            sub = Submission(
                work_base=self.param["_base"],
                machine=self.machine,
                resources=self.resources,
                task_list=tasks,
            )
            sub.run_submission()
            print(f"  Step {step.name} complete")
            step.collect()

        print()
        print("========== Done ==========")
