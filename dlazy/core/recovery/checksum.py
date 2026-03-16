"""Checksum utilities using xxh64 algorithm (with fallback to hashlib)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import hashlib

try:
    import xxhash

    XXHASH_AVAILABLE = True
except ImportError:
    xxhash = None  # type: ignore
    XXHASH_AVAILABLE = False


def _compute_xxh64(file_path: Path) -> str:
    assert xxhash is not None
    hasher = xxhash.xxh64()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _compute_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_checksum(file_path: Path, algorithm: str = "xxh64") -> str:
    """Compute checksum of a file.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm (default: xxh64, falls back to sha256 if xxhash unavailable)

    Returns:
        Hexadecimal checksum string

    Raises:
        ValueError: If algorithm is not supported
        FileNotFoundError: If file does not exist
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if algorithm == "xxh64":
        if XXHASH_AVAILABLE:
            return _compute_xxh64(file_path)
        return _compute_sha256(file_path)
    elif algorithm == "sha256":
        return _compute_sha256(file_path)
    else:
        raise ValueError(
            f"Unsupported algorithm: {algorithm}. Supported: xxh64, sha256."
        )


def verify_checksum(file_path: Path, expected: str) -> bool:
    """Verify file checksum matches expected value.

    Args:
        file_path: Path to the file
        expected: Expected checksum string

    Returns:
        True if checksum matches, False otherwise
    """
    try:
        actual = compute_checksum(file_path)
        return actual == expected
    except (FileNotFoundError, ValueError):
        return False


def compute_checksum_dict(file_path: Path) -> Dict[str, Any]:
    """Compute checksum with metadata.

    Args:
        file_path: Path to the file

    Returns:
        Dict with 'checksum', 'algorithm', 'size', 'mtime' keys
    """
    file_path = Path(file_path)
    stat = file_path.stat()

    return {
        "checksum": compute_checksum(file_path),
        "algorithm": "xxh64",
        "size": stat.st_size,
        "mtime": stat.st_mtime,
    }


def verify_checksum_dict(file_path: Path, checksum_dict: Dict[str, Any]) -> bool:
    """Verify file against a checksum dictionary.

    Args:
        file_path: Path to the file
        checksum_dict: Dictionary with checksum info

    Returns:
        True if all checks pass
    """
    file_path = Path(file_path)

    if not file_path.exists():
        return False

    # Check size first (fast)
    if "size" in checksum_dict:
        if file_path.stat().st_size != checksum_dict["size"]:
            return False

    # Check checksum
    if "checksum" in checksum_dict:
        expected = checksum_dict["checksum"]
        algorithm = checksum_dict.get("algorithm", "xxh64")

        if algorithm != "xxh64":
            return False

        return verify_checksum(file_path, expected)

    return True
