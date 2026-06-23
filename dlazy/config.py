import json
import sys
from pathlib import Path

from dpdispatcher import Machine, Resources


def load_param(path):
    with open(path) as f:
        param = json.load(f)
    base = Path(path).resolve().parent
    for key in ("structures", "work_dir"):
        if key in param:
            param[key] = str((base / param[key]).resolve())
    steps = param.get("steps", [])
    for s in steps:
        for k in ("structures", "work_dir"):
            if k in s:
                s[k] = str((base / s[k]).resolve())
    param["_base"] = str(base)
    openmx = param.get("openmx", {})
    for key in ("module_path", "deeph_dir"):
        if key in openmx:
            openmx[key] = str((base / openmx[key]).resolve())
    if "mpi_cmd" not in param:
        param["mpi_cmd"] = "mpirun -np {cpus}"
    return param


def load_machine(path):
    with open(path) as f:
        cfg = json.load(f)
    base = Path(path).resolve().parent
    machine = Machine.load_from_dict(cfg["machine"])
    resources = Resources.load_from_dict(cfg["resources"])
    return machine, resources


def resolve_openmx_generator(param):
    module_path = param.get("openmx", {}).get("module_path")
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
