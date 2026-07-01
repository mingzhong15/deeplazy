"""Unit tests for dlazy.config: param/machine loading, mode validation."""
import json
import tempfile
from pathlib import Path

import pytest

from dlazy import config


def _write_param(d, **overrides):
    p = {
        "name": "test",
        "structures": "structures.txt",
        "work_dir": "work",
        "steps": [{"name": "olp", "type": "olp"}],
    }
    p.update(overrides)
    path = Path(d) / "param.json"
    path.write_text(json.dumps(p))
    (Path(d) / "structures.txt").touch()
    return path


def test_load_param_defaults_to_easy_mode():
    with tempfile.TemporaryDirectory() as d:
        p = _write_param(d)
        param = config.load_param(p)
        assert param["mode"] == "easy"


def test_load_param_accepts_massive_mode():
    with tempfile.TemporaryDirectory() as d:
        p = _write_param(d, mode="massive")
        param = config.load_param(p)
        assert param["mode"] == "massive"


def test_load_param_rejects_unknown_mode():
    with tempfile.TemporaryDirectory() as d:
        p = _write_param(d, mode="bogus")
        with pytest.raises(ValueError, match="Unknown mode"):
            config.load_param(p)


def test_load_param_resolves_structures_absolute():
    with tempfile.TemporaryDirectory() as d:
        p = _write_param(d)
        param = config.load_param(p)
        assert Path(param["structures"]).is_absolute()
        assert param["structures"].endswith("structures.txt")


def test_load_param_resolves_work_dir_absolute():
    with tempfile.TemporaryDirectory() as d:
        p = _write_param(d)
        param = config.load_param(p)
        assert Path(param["work_dir"]).is_absolute()
        assert param["work_dir"].endswith("work")


def test_load_param_keeps_base():
    with tempfile.TemporaryDirectory() as d:
        p = _write_param(d)
        param = config.load_param(p)
        assert param["_base"] == str(Path(d).resolve())


def _write_machine(d, **overrides):
    m = {
        "machine": {"batch_type": "Slurm", "context_type": "LocalContext",
                     "local_root": ".", "remote_root": "."},
        "resources": {"number_node": 1, "cpu_per_node": 64,
                       "queue_name": "normal", "group_size": 50},
        "olp": {"executable": "openmx", "data_path": "data",
                 "mpi_cmd": "mpirun -np {cpus}"},
        "fp": {"executable": "openmx", "data_path": "data",
                "mpi_cmd": "mpirun -np {cpus}", "cpus_per_task": 24},
        "job_name_prefix": "test",
    }
    m.update(overrides)
    path = Path(d) / "machine.json"
    path.write_text(json.dumps(m))
    (Path(d) / "data").mkdir()
    return path


def test_load_machine_easy_returns_slurm():
    with tempfile.TemporaryDirectory() as d:
        p = _write_machine(d)
        machine, resources, mcfg = config.load_machine(p)
        assert type(machine).__name__ == "Slurm"


def test_load_machine_massive_returns_slurmjobarray():
    with tempfile.TemporaryDirectory() as d:
        p = _write_machine(d)
        machine, resources, mcfg = config.load_machine_massive(p)
        assert type(machine).__name__ == "SlurmJobArray"
        assert resources.kwargs.get("slurm_job_size") == 1


def test_load_machine_massive_preserves_kwargs_override():
    with tempfile.TemporaryDirectory() as d:
        p = _write_machine(d, resources={
            "number_node": 1, "cpu_per_node": 64,
            "queue_name": "normal", "group_size": 50,
            "kwargs": {"slurm_job_size": 5},
        })
        machine, resources, mcfg = config.load_machine_massive(p)
        # load_machine_massive uses setdefault, so explicit user value wins
        assert resources.kwargs.get("slurm_job_size") == 5


def test_load_machine_section_keys():
    with tempfile.TemporaryDirectory() as d:
        p = _write_machine(d)
        machine, resources, mcfg = config.load_machine(p)
        for section in ("olp", "infer", "fp", "deeph", "massive", "job_name_prefix"):
            assert section in mcfg, f"missing section {section}"


def test_resolve_openmx_generator_returns_class():
    from dlazy.generator import OpenMXGenerator
    assert config.resolve_openmx_generator() is OpenMXGenerator


def test_find_latest_deeph_dir_returns_none_for_empty():
    with tempfile.TemporaryDirectory() as d:
        assert config.find_latest_deeph_dir([d]) is None


def test_find_latest_deeph_dir_returns_none_for_missing():
    assert config.find_latest_deeph_dir(["/nonexistent"]) is None


def test_find_latest_deeph_dir_finds_dft_subdir():
    with tempfile.TemporaryDirectory() as d:
        ts = Path(d) / "20240101_120000"
        dft = ts / "dft"
        dft.mkdir(parents=True)
        result = config.find_latest_deeph_dir([d])
        assert result is not None
        assert result.endswith("/dft")
