"""HDF5 integrity validator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from dlazy.core.validator.base import Validator, ValidationResult
from dlazy.core.validator.registry import register_validator

try:
    import h5py

    HAS_H5PY = True
except ImportError:
    HAS_H5PY = False


@register_validator("hdf5_integrity")
class HDF5IntegrityValidator(Validator):
    """Validator for HDF5 file integrity.

    Checks file structure, required datasets, and data validity.
    """

    validator_type = "hdf5_integrity"

    def __init__(
        self,
        required_datasets: Optional[List[str]] = None,
        check_nan: bool = True,
        check_inf: bool = True,
        check_empty: bool = True,
    ):
        """Initialize HDF5 integrity validator.

        Args:
            required_datasets: List of required dataset names
            check_nan: Check for NaN values
            check_inf: Check for Inf values
            check_empty: Check for empty datasets
        """
        self.required_datasets = required_datasets or []
        self.check_nan = check_nan
        self.check_inf = check_inf
        self.check_empty = check_empty

    def validate(self, path: Path) -> ValidationResult:
        """Validate HDF5 file integrity.

        Args:
            path: Path to HDF5 file

        Returns:
            ValidationResult with integrity status
        """
        path = Path(path)

        if not HAS_H5PY:
            return ValidationResult(
                is_valid=False,
                errors=["h5py not installed, cannot validate HDF5 files"],
            )

        if not path.exists():
            return ValidationResult(
                is_valid=False,
                errors=[f"File not found: {path}"],
            )

        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {}

        # Check if file can be opened
        try:
            with h5py.File(path, "r") as f:
                details["datasets"] = list(f.keys())
                details["attrs"] = dict(f.attrs)

                # Check required datasets
                missing = self._check_required_datasets(f)
                if missing:
                    errors.append(f"Missing required datasets: {missing}")

                # Check each dataset for NaN/Inf/Empty
                for name in f.keys():
                    dataset_errors = self._validate_dataset(f[name], name)
                    errors.extend(dataset_errors)

        except OSError as e:
            errors.append(f"Failed to open HDF5 file: {e}")
        except Exception as e:
            errors.append(f"HDF5 validation error: {e}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details,
        )

    def _check_required_datasets(self, h5file: "h5py.File") -> List[str]:
        """Check for required datasets.

        Args:
            h5file: Open HDF5 file

        Returns:
            List of missing dataset names
        """
        missing = []
        for name in self.required_datasets:
            if name not in h5file:
                missing.append(name)
        return missing

    def _validate_dataset(self, dataset: "h5py.Dataset", name: str) -> List[str]:
        """Validate a single dataset.

        Args:
            dataset: HDF5 dataset
            name: Dataset name

        Returns:
            List of error messages
        """
        errors = []

        try:
            data = dataset[()]

            # Check for empty
            if self.check_empty:
                if data is None or (hasattr(data, "size") and data.size == 0):
                    errors.append(f"Dataset '{name}' is empty")
                    return errors

            # Only check numeric data for NaN/Inf
            if not np.issubdtype(data.dtype, np.number):
                return errors

            # Check for NaN
            if self.check_nan and np.any(np.isnan(data)):
                nan_count = np.sum(np.isnan(data))
                errors.append(f"Dataset '{name}' contains {nan_count} NaN values")

            # Check for Inf
            if self.check_inf and np.any(np.isinf(data)):
                inf_count = np.sum(np.isinf(data))
                errors.append(f"Dataset '{name}' contains {inf_count} Inf values")

        except Exception as e:
            errors.append(f"Failed to validate dataset '{name}': {e}")

        return errors


def check_file_openable(path: Path) -> bool:
    """Check if HDF5 file can be opened.

    Args:
        path: Path to HDF5 file

    Returns:
        True if file can be opened
    """
    if not HAS_H5PY:
        return False

    path = Path(path)
    if not path.exists():
        return False

    try:
        with h5py.File(path, "r") as f:
            return True
    except Exception:
        return False


def check_required_datasets(path: Path, required: List[str]) -> List[str]:
    """Check for required datasets in HDF5 file.

    Args:
        path: Path to HDF5 file
        required: List of required dataset names

    Returns:
        List of missing dataset names
    """
    if not HAS_H5PY:
        return required

    path = Path(path)
    if not path.exists():
        return required

    try:
        with h5py.File(path, "r") as f:
            return [name for name in required if name not in f]
    except Exception:
        return required


def check_nan_inf(path: Path) -> Dict[str, Tuple[int, int]]:
    """Check for NaN and Inf values in HDF5 datasets.

    Args:
        path: Path to HDF5 file

    Returns:
        Dict mapping dataset names to (nan_count, inf_count) tuples
    """
    if not HAS_H5PY:
        return {}

    path = Path(path)
    if not path.exists():
        return {}

    result = {}

    try:
        with h5py.File(path, "r") as f:
            for name in f.keys():
                try:
                    data = f[name][()]
                    if np.issubdtype(data.dtype, np.number):
                        result[name] = (
                            int(np.sum(np.isnan(data))),
                            int(np.sum(np.isinf(data))),
                        )
                except Exception:
                    pass
    except Exception:
        pass

    return result


def get_dataset_info(path: Path) -> Dict[str, Dict[str, Any]]:
    """Get information about datasets in HDF5 file.

    Args:
        path: Path to HDF5 file

    Returns:
        Dict mapping dataset names to info dicts
    """
    if not HAS_H5PY:
        return {}

    path = Path(path)
    if not path.exists():
        return {}

    result = {}

    try:
        with h5py.File(path, "r") as f:
            for name in f.keys():
                dataset = f[name]
                result[name] = {
                    "shape": dataset.shape,
                    "dtype": str(dataset.dtype),
                    "size": dataset.size,
                }
    except Exception:
        pass

    return result
