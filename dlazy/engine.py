from dpdispatcher import Submission

from . import config, steps


class Workflow:
    def __init__(self, param_path, machine_path):
        self.param = config.load_param(param_path)
        self.machine, self.resources = config.load_machine(machine_path)
        self.ctx = {}

    def run(self, step_filter=None, dry_run=False):
        name = self.param.get("name", "workflow")
        step_defs = self.param.get("steps", [])

        print(f"========== dlazy: {name} ==========")
        print(f"Structures: {self.param.get('structures', '?')}")
        total_steps = len(step_defs)
        print(f"Steps:      {total_steps}")
        if self.resources.group_size:
            print(f"Group size: {self.resources.group_size} tasks/job")
        print()

        for i, defn in enumerate(step_defs):
            if step_filter and defn["name"] != step_filter:
                continue

            step = steps.create_step(defn, self.param, self.ctx)
            print(f"--- Step {i+1}/{total_steps}: {step.name} ---")

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

            sub = Submission(
                work_base=self.param["work_dir"],
                machine=self.machine,
                resources=self.resources,
                task_list=tasks,
            )
            sub.run_submission()
            print(f"  Step {step.name} complete")
            step.collect()

        print()
        print("========== Done ==========")
