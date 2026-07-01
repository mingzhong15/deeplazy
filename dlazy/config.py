import json
from pathlib import Path

from dpdispatcher import Machine, Resources


def load_param(path):
    with open(path) as f:
        param = json.load(f)
    base = Path(path).resolve().parent
    for key in ("structures",):
        if key in param:
            param[key] = str((base / param[key]).resolve())
    wd = param.get("work_dir")
    if wd:
        param["work_dir"] = str((base / wd).resolve())
    param["_base"] = str(base)
    param.setdefault("mode", "easy")
    if param["mode"] not in ("easy", "massive"):
        raise ValueError(f"Unknown mode: {param['mode']!r}, must be 'easy' or 'massive'")
    return param


def load_machine(path):
    """Load machine.json in easy mode (uses batch_type as-is)."""
    return _load_machine(path, massive=False)


def load_machine_massive(path):
    """Load machine.json for massive mode (forces SlurmJobArray, sets
    resources.kwargs.slurm_job_size=1).

    SlurmJobArray is a dpdispatcher built-in (registered via
    __init_subclass__). Each Task becomes one array element; dlazy steps
    build one Task per K-structure manifest, so 1 array element runs K
    structures via dlazy/_runner.py.
    """
    return _load_machine(path, massive=True)


def _load_machine(path, massive=False):
    with open(path) as f:
        cfg = json.load(f)
    base = Path(path).resolve().parent

    machine_dict = dict(cfg["machine"])
    if massive:
        machine_dict["batch_type"] = "SlurmJobArray"
    machine = Machine.load_from_dict(machine_dict)

    res_dict = dict(cfg["resources"])
    if massive:
        res_dict.setdefault("kwargs", {})
        res_dict["kwargs"].setdefault("slurm_job_size", 1)
    resources = Resources.load_from_dict(res_dict)

    mcfg = {}
    for section in ("olp", "infer", "fp", "deeph"):
        sec = dict(cfg.get(section, {}))
        for key in ("executable", "data_path", "infer_toml"):
            if key in sec:
                sec[key] = str((base / sec[key]).resolve())
        mcfg[section] = sec

    mcfg["job_name_prefix"] = cfg.get("job_name_prefix")
    mcfg["massive"] = dict(cfg.get("massive", {}))

    return machine, resources, mcfg


def find_latest_deeph_dir(search_dirs):
    for d in search_dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        ts_dirs = sorted([x for x in p.iterdir() if x.is_dir()], reverse=True)
        for ts in ts_dirs:
            dft = ts / "dft"
            if dft.is_dir():
                return str(dft)
    return None


def resolve_openmx_generator():
    from dlazy.generator import OpenMXGenerator as Gen
    return Gen
