"""Tests for HDF5 integrity validator."""

import pytest

from dlazy.core.validator.hdf5_integrity import (
    HDF5IntegrityValidator,
    check_file_openable,
    check_required_datasets,
)


class TestHDF5IntegrityValidator:
    """Tests for HDF5IntegrityValidator."""

    def test_validate_valid_hdf5(self, sample_hdf5):
        validator = HDF5IntegrityValidator()
        result = validator.validate(sample_hdf5)

        assert result.is_valid

    def test_validate_nonexistent_file(self, tmp_path):
        validator = HDF5IntegrityValidator()
        result = validator.validate(tmp_path / "nonexistent.h5")

        assert not result.is_valid
        assert "not found" in result.errors[0].lower()

    def test_validate_invalid_format(self, tmp_path):
        invalid_file = tmp_path / "output.h5"
        invalid_file.write_bytes(b"not an hdf5 file")

        validator = HDF5IntegrityValidator()
        result = validator.validate(invalid_file)

        assert not result.is_valid

    def test_validate_corrupted_file(self, tmp_path):
        corrupted = tmp_path / "corrupted.h5"
        corrupted.write_bytes(b"\x00" * 100)

        validator = HDF5IntegrityValidator()
        result = validator.validate(corrupted)

        assert not result.is_valid

    def test_validate_required_datasets_present(self, tmp_path):
        import h5py

        h5_file = tmp_path / "test.h5"
        with h5py.File(h5_file, "w") as f:
            f.create_dataset("hamiltonian", data=[[1.0, 0.0], [0.0, 1.0]])
            f.create_dataset("overlap", data=[[1.0, 0.0], [0.0, 1.0]])

        validator = HDF5IntegrityValidator(required_datasets=["hamiltonian", "overlap"])
        result = validator.validate(h5_file)

        assert result.is_valid

    def test_validate_missing_required_dataset(self, tmp_path):
        import h5py

        h5_file = tmp_path / "test.h5"
        with h5py.File(h5_file, "w") as f:
            f.create_dataset("hamiltonian", data=[[1.0, 0.0], [0.0, 1.0]])

        validator = HDF5IntegrityValidator(required_datasets=["hamiltonian", "overlap"])
        result = validator.validate(h5_file)

        assert not result.is_valid
        assert any("overlap" in e for e in result.errors)

    def test_validate_nan_values(self, nan_values_h5):
        validator = HDF5IntegrityValidator(check_nan=True)
        result = validator.validate(nan_values_h5)

        assert not result.is_valid
        assert any("NaN" in e for e in result.errors)

    def test_check_file_openable(self, sample_hdf5):
        assert check_file_openable(sample_hdf5)

    def test_check_file_openable_nonexistent(self, tmp_path):
        assert not check_file_openable(tmp_path / "nonexistent.h5")

    def test_check_required_datasets(self, tmp_path):
        import h5py

        h5_file = tmp_path / "test.h5"
        with h5py.File(h5_file, "w") as f:
            f.create_dataset("hamiltonian", data=[[1.0, 0.0], [0.0, 1.0]])

        missing = check_required_datasets(h5_file, ["hamiltonian", "overlap"])
        assert "overlap" in missing
        assert "hamiltonian" not in missing
