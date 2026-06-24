from pathlib import Path

from dpdispatcher import Task

from . import register_step
from .. import config


@register_step("infer")
class InferStep:
    name: str = ""
    type: str = "infer"

    def __init__(self, defn, param, mcfg, ctx):
        self.defn = defn
        self.param = param
        self.mcfg = mcfg
        self.ctx = ctx
        self.name = defn["name"]

    def prepare(self):
        work_dir = Path(self.param["work_dir"])
        deeph = self.mcfg.get("deeph", {})
        executable = deeph.get("executable", "deepx")
        infer_toml_src = deeph.get("infer_toml")
        if not infer_toml_src:
            print("  WARNING: deeph.infer_toml not set in machine.json")
            return []

        infer_toml_src = Path(infer_toml_src)
        if not infer_toml_src.exists():
            print(f"  WARNING: infer.toml not found: {infer_toml_src}")
            return []

        infer_dir = work_dir / "inference"
        outputs_dir = infer_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        latest = config.find_latest_deeph_dir([str(outputs_dir)])
        if latest:
            print(f"  skip (done): inference already available at {latest}")
            return []

        inputs_dir = deeph.get("inputs_dir")
        local_inputs = infer_dir / "inputs"
        if inputs_dir and not local_inputs.exists():
            src = Path(inputs_dir)
            if src.is_dir():
                local_inputs.symlink_to(src, target_is_directory=True)
                print(f"  link inputs: {local_inputs} -> {src}")

        model_dir = self.param.get("deeph_model")
        if model_dir:
            model_dir = str(Path(model_dir).resolve())
        else:
            print("  WARNING: deeph_model not set in param.json")
            return []

        toml_text = infer_toml_src.read_text()
        toml_text = toml_text.replace("{inputs_dir}", str(local_inputs.resolve()))
        toml_text = toml_text.replace("{outputs_dir}", str(outputs_dir))
        toml_text = toml_text.replace("{model_dir}", model_dir)

        task_toml = work_dir / "_infer.toml"
        task_toml.write_text(toml_text)
        print(f"  gen: _infer.toml (model={model_dir})")

        forward = ["_infer.toml"]
        if local_inputs.exists() and local_inputs.is_symlink():
            target = local_inputs.resolve()
            if target.exists():
                forward.append(str(local_inputs.relative_to(work_dir)))

        tasks = [Task(
            command=f"{executable} infer _infer.toml",
            task_work_path=".",
            forward_files=forward,
            backward_files=["inference/outputs"],
            outlog="infer.out",
        )]
        return tasks

    def collect(self):
        outputs_dir = Path(self.param["work_dir"]) / "inference" / "outputs"
        latest = config.find_latest_deeph_dir([str(outputs_dir)])
        if latest:
            self.ctx["_deeph_dir"] = latest
            n = len(list(Path(latest).iterdir())) if Path(latest).is_dir() else 0
            print(f"  deeph_dir: {latest} ({n} structures)")
