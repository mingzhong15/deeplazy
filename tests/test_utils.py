"""Unit tests for dlazy.utils: natural sort, structures parsing, finished check."""
import tempfile
from pathlib import Path

import pytest

from dlazy import utils


def test_natural_key_sorts_digits_by_value():
    names = ["hamiltonians_step10.h5", "hamiltonians_step2.h5",
             "hamiltonians_step1.h5", "hamiltonians_step22.h5"]
    paths = [Path(n) for n in names]
    sorted_paths = sorted(paths, key=utils.natural_key)
    assert [p.name for p in sorted_paths] == [
        "hamiltonians_step1.h5",
        "hamiltonians_step2.h5",
        "hamiltonians_step10.h5",
        "hamiltonians_step22.h5",
    ]


def test_find_final_hamiltonian_picks_highest_step():
    with tempfile.TemporaryDirectory() as d:
        for n in [1, 2, 10, 22]:
            (Path(d) / f"hamiltonians_step{n}.h5").touch()
        result = utils.find_final_hamiltonian(d)
        assert Path(result).name == "hamiltonians_step22.h5"


def test_find_final_hamiltonian_returns_none_when_empty():
    with tempfile.TemporaryDirectory() as d:
        assert utils.find_final_hamiltonian(d) is None


def test_find_final_hamiltonian_returns_none_when_no_match():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "other.h5").touch()
        (Path(d) / "hamiltonians_notstep.h5").touch()
        assert utils.find_final_hamiltonian(d) is None


def test_check_finished_detects_normal_termination():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "openmx.std"
        p.write_text("some output\nnormally finished\n")
        assert utils.check_finished(p) is True


def test_check_finished_returns_false_when_not_finished():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "openmx.std"
        p.write_text("some output\n")
        assert utils.check_finished(p) is False


def test_check_finished_returns_false_when_missing():
    assert utils.check_finished(Path("/nonexistent/openmx.std")) is False


def test_read_structures_parses_absolute_paths():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "list.txt"
        poscar1 = Path(d) / "s1.vasp"
        poscar2 = Path(d) / "s2.vasp"
        for p in (poscar1, poscar2):
            p.touch()
        f.write_text(f"{poscar1}\n{poscar2}\n\n")
        result = utils.read_structures(str(f))
        assert len(result) == 2
        assert result[0][0] == "s1"
        assert result[1][0] == "s2"
        assert result[0][1] == str(poscar1.resolve())


def test_read_structures_parses_relative_paths():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        (base / "s1.vasp").touch()
        (base / "s2.vasp").touch()
        f = base / "list.txt"
        f.write_text("s1.vasp\ns2.vasp\n")
        result = utils.read_structures(str(f))
        assert len(result) == 2
        assert result[0][0] == "s1"
        assert Path(result[0][1]).name == "s1.vasp"


def test_make_mpi_cmd_substitutes_cpus():
    cmd = utils.make_mpi_cmd("mpirun -np {cpus}", "openmx", 24)
    assert cmd == "mpirun -np 24 openmx openmx_in.dat > openmx.std"
