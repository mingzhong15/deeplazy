from pathlib import Path

from dpdispatcher import Task

from . import register_step
from .. import config
from .. import utils


# ── TOML helpers ──────────────────────────────────────────────────────────────

def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        items = ", ".join(_toml_value(x) for x in v)
        return f"[{items}]"
    return str(v)


def _dict_to_toml(d, prefix=""):
    lines = []
    has_leaf = any(not isinstance(v, dict) for v in d.values())
    if prefix and has_leaf:
        lines.append(f"[{prefix}]")
    for key, value in d.items():
        if isinstance(value, dict):
            sub = f"{prefix}.{key}" if prefix else key
            lines.append(_dict_to_toml(value, sub))
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines)


def generate_infer_toml(*, inputs_dir, outputs_dir, model_dir,
                        workflow_name="workflow", deeph=None):
    deeph = deeph or {}
    cfg = {
        "system": {
            "note": f"dlazy: {workflow_name}",
            "device": deeph.get("device", "cpu"),
            "float_type": deeph.get("float_type", "fp32"),
            "random_seed": deeph.get("random_seed", 137),
            "log_level": deeph.get("log_level", "info"),
            "jax_memory_preallocate": False,
        },
        "data": {
            "inputs_dir": inputs_dir,
            "outputs_dir": outputs_dir,
            "dft": {"data_dir_depth": 0},
            "graph": {
                "dataset_name": workflow_name.upper(),
                "graph_type": "HS",
                "storage_type": "disk",
                "disk_shards_num": 1,
                "disk_shards_indices": [],
                "disk_mem_buffer_size": 2048,
                "parallel_num": -1,
                "only_save_graph": False,
            },
        },
        "model": {
            "model_dir": model_dir,
            "load_model_type": "best",
            "load_model_epoch": -1,
        },
        "process": {
            "infer": {
                "output_type": "h5",
                "output_into": "to_output",
                "target_symmetrize": True,
                "multi_way_jit_num": deeph.get("jit_num", 4),
                "dataloader": {"batch_size": deeph.get("batch_size", 1)},
            },
        },
    }
    return _dict_to_toml(cfg)


# ── Step ──────────────────────────────────────────────────────────────────────

@register_step("deeph")
class DeepHStep:
    name: str = ""
    type: str = "deeph"

    def __init__(self, defn, param, mcfg, ctx):
        self.defn = defn
        self.param = param
        self.mcfg = mcfg
        self.ctx = ctx
        self.name = defn["name"]

    def _resolve(self, key):
        val = self.defn.get(key)
        if not val:
            return None
        return str((Path(self.param["_base"]) / val).resolve())

    def _get_infer_toml(self, work_dir, local_inputs, outputs_dir, model_dir):
        deeph = self.mcfg.get("deeph", {})
        src = deeph.get("infer_toml")

        if src:
            src_path = Path(src)
            if src_path.exists():
                text = src_path.read_text()
                text = text.replace("{inputs_dir}", str(local_inputs.resolve()))
                text = text.replace("{outputs_dir}", str(outputs_dir))
                text = text.replace("{model_dir}", model_dir)
                return text

        return generate_infer_toml(
            inputs_dir=str(local_inputs.resolve()),
            outputs_dir=str(outputs_dir),
            model_dir=model_dir,
            workflow_name=self.param.get("name", "workflow"),
            deeph=deeph,
        )

    def prepare(self):
        work_dir = Path(self.param["work_dir"])
        deeph = self.mcfg.get("deeph", {})
        executable = deeph.get("executable", "deepx")

        infer_dir = work_dir / "inference"
        outputs_dir = infer_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        force = self.defn.get("force", False)
        latest = config.find_latest_deeph_dir([str(outputs_dir)])

        if force:
            print("  force: re-running inference (force=True)")
            latest = None
        elif latest:
            structures = utils.read_structures(self.param["structures"])
            needed = {sid for sid, _ in structures}
            existing = {p.parent.name for p in Path(latest).glob("*/hamiltonian_pred.h5")}
            missing = needed - existing

            if missing:
                print(f"  partial: {len(existing)}/{len(needed)} structures done, "
                      f"{len(missing)} missing, re-running inference")
                latest = None
            else:
                print(f"  skip (done): inference already available at {latest}")
                return []

        inputs_dir = self._resolve("inputs_dir")
        local_inputs = infer_dir / "inputs"
        if inputs_dir and not local_inputs.exists():
            src = Path(inputs_dir)
            if src.is_dir():
                local_inputs.symlink_to(src, target_is_directory=True)
                print(f"  link inputs: {local_inputs} -> {src}")

        model_dir = self._resolve("model")
        if model_dir is None:
            print("  WARNING: step.defn.model not set in param.json")
            return []

        toml_text = self._get_infer_toml(work_dir, local_inputs, outputs_dir, model_dir)
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
            backward_files=["inference/outputs/*/dft/**", "inference/outputs/*/deepx.log"],
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
