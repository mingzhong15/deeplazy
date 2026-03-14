"""Shared pytest fixtures for dlazy tests."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import h5py
import numpy as np


# ============================================================================
# Directory fixtures
# ============================================================================


@pytest.fixture
def temp_workdir():
    """Create a temporary working directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_config_file(temp_workdir):
    """Create a temporary config file."""
    config_path = temp_workdir / "config.yaml"
    config_content = """
0olp:
  nodes: 1
  ppn: 24
  time_limit: "1:00:00"

1infer:
  nodes: 1
  ppn: 1
  time_limit: "2:00:00"
  num_groups: 10

2calc:
  nodes: 1
  ppn: 24
  time_limit: "2:00:00"

software:
  python: "python3"
  openmx: "/path/to/openmx"
"""
    config_path.write_text(config_content)
    return config_path


# ============================================================================
# HDF5 fixtures
# ============================================================================


@pytest.fixture
def sample_hdf5(temp_workdir):
    """Create a sample HDF5 file for general testing."""
    path = temp_workdir / "sample.h5"
    with h5py.File(path, "w") as f:
        f.create_dataset("data", data=np.random.rand(5, 5))
        f.attrs["test"] = "sample"
    return path


@pytest.fixture
def valid_overlaps_h5(temp_workdir):
    """Create a valid overlaps HDF5 file."""
    path = temp_workdir / "valid_overlaps.h5"
    with h5py.File(path, "w") as f:
        f.create_dataset("overlaps", data=np.random.rand(10, 10, 10, 10))
        f.attrs["description"] = "Sample overlap matrix"
    return path


@pytest.fixture
def valid_hamiltonians_h5(temp_workdir):
    """Create a valid Hamiltonians HDF5 file."""
    path = temp_workdir / "valid_hamiltonians.h5"
    with h5py.File(path, "w") as f:
        # Create sample Hamiltonian data
        f.create_dataset(
            "hamiltonians",
            data=np.random.rand(10, 10, 10) + 1j * np.random.rand(10, 10, 10),
        )
        f.attrs["description"] = "Sample Hamiltonian matrix"
    return path


@pytest.fixture
def corrupted_h5(temp_workdir):
    """Create a corrupted HDF5 file (invalid format)."""
    path = temp_workdir / "corrupted.h5"
    # Write invalid HDF5 bytes
    with open(path, "wb") as f:
        f.write(b"This is not a valid HDF5 file content")
    return path


@pytest.fixture
def empty_h5(temp_workdir):
    """Create an empty but valid HDF5 file."""
    path = temp_workdir / "empty.h5"
    with h5py.File(path, "w") as f:
        # No datasets, just an empty file
        pass
    return path


@pytest.fixture
def nan_values_h5(temp_workdir):
    """Create an HDF5 file with NaN/Inf values."""
    path = temp_workdir / "nan_values.h5"
    with h5py.File(path, "w") as f:
        # Create data with NaN and Inf values
        data = np.array([1.0, np.nan, 2.0, np.inf, 3.0, -np.inf])
        f.create_dataset("overlaps", data=data)
    return path


@pytest.fixture
def missing_datasets_h5(temp_workdir):
    """Create an HDF5 file with missing required datasets."""
    path = temp_workdir / "missing_datasets.h5"
    with h5py.File(path, "w") as f:
        # Create wrong dataset names
        f.create_dataset("wrong_name", data=np.random.rand(5, 5))
    return path


# ============================================================================
# OpenMX output fixtures
# ============================================================================


@pytest.fixture
def scf_converged_out(temp_workdir):
    """Create a converged SCF output file."""
    path = temp_workdir / "scf_converged.out"
    content = """
OpenMX Ver. 3.9
Calculation started at: 2026-03-14 10:00:00

SCF iteration 1: Energy = -100.5 eV
SCF iteration 2: Energy = -105.2 eV
SCF iteration 3: Energy = -106.1 eV
SCF iteration 4: Energy = -106.3 eV
SCF iteration 5: Energy = -106.4 eV
SCF iteration 6: Energy = -106.42 eV
SCF iteration 7: Energy = -106.43 eV
SCF iteration 8: Energy = -106.431 eV
SCF iteration 9: Energy = -106.432 eV
SCF iteration 10: Energy = -106.432 eV

SCF convergence achieved!
Total energy = -106.432 eV

Calculation completed successfully.
"""
    path.write_text(content)
    return path


@pytest.fixture
def scf_not_converged_out(temp_workdir):
    """Create a non-converged SCF output file."""
    path = temp_workdir / "scf_not_converged.out"
    lines = ["OpenMX Ver. 3.9", "Calculation started at: 2026-03-14 10:00:00", ""]
    for i in range(1, 101):
        lines.append(f"SCF iteration {i}: Energy = -{100 + i * 0.1:.3f} eV")
    lines.append("")
    lines.append("SCF NOT CONVERGED after 100 iterations")
    lines.append("")
    lines.append("Calculation failed.")
    path.write_text("\n".join(lines))
    return path


# ============================================================================
# Mock fixtures
# ============================================================================


@pytest.fixture
def mock_slurm():
    """Mock SLURM commands for testing."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Submitted batch job 12345", stderr=""
        )
        yield mock_run


@pytest.fixture
def mock_squeue():
    """Mock squeue output for testing."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="12345|R|test_job", stderr=""
        )
        yield mock_run


@pytest.fixture
def mock_sacct():
    """Mock sacct output for testing."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="12345|COMPLETED", stderr=""
        )
        yield mock_run


# ============================================================================
# Sample config fixture
# ============================================================================


@pytest.fixture
def sample_config():
    """Return a sample configuration dictionary."""
    return {
        "0olp": {
            "nodes": 1,
            "ppn": 24,
            "time_limit": "1:00:00",
            "partition": "normal",
        },
        "1infer": {
            "nodes": 1,
            "ppn": 1,
            "time_limit": "2:00:00",
            "num_groups": 10,
        },
        "2calc": {
            "nodes": 1,
            "ppn": 24,
            "time_limit": "2:00:00",
        },
        "software": {
            "python": "python3",
            "openmx": "/path/to/openmx",
        },
    }
