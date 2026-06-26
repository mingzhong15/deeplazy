import json
import sys
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
        param["_work_dir_rel"] = wd
        param["work_dir"] = str((base / wd).resolve())
    dm = param.get("deeph_model")
    if dm:
        param["deeph_model"] = str((base / dm).resolve())
    param["_base"] = str(base)
    return param


def load_machine(path):
    with open(path) as f:
        cfg = json.load(f)
    base = Path(path).resolve().parent
    machine = Machine.load_from_dict(cfg["machine"])
    resources = Resources.load_from_dict(cfg["resources"])

    mcfg = {}
    for section in ("olp", "infer", "fp"):
        sec = dict(cfg.get(section, {}))
        for key in ("executable", "mpi_cmd", "data_path", "module_path", "infer_toml"):
            if key in sec:
                sec[key] = str((base / sec[key]).resolve())
            elif key == "mpi_cmd" and "mpi_cmd" not in sec:
                pass  # optional
        mcfg[section] = sec

    mcfg["job_name_prefix"] = cfg.get("job_name_prefix")

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


def resolve_openmx_generator(module_path=None):
    if module_path:
        if module_path not in sys.path:
            sys.path.insert(0, module_path)
    try:
        from input_from_mind.openmx import OpenMXGenerator as Gen
    except ImportError:
        try:
            from dlazy.generator import OpenMXGenerator as Gen
        except ImportError:
            Gen = None
    return Gen
