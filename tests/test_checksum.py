"""Tests for checksum utilities."""

import pytest
from pathlib import Path
import tempfile

from dlazy.core.recovery.checksum import (
    compute_checksum,
    verify_checksum,
    compute_checksum_dict,
    verify_checksum_dict,
)


def test_compute_checksum():
    """Test compute_checksum returns 16-char hex string."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content for checksum")
        f.flush()
        path = Path(f.name)

    checksum = compute_checksum(path)

    assert isinstance(checksum, str)
    assert len(checksum) == 16  # xxh64 produces 16 hex chars
    path.unlink()


def test_compute_checksum_consistency():
    """Test that compute_checksum is consistent for same content."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content")
        f.flush()
        path = Path(f.name)

    checksum1 = compute_checksum(path)
    checksum2 = compute_checksum(path)

    assert checksum1 == checksum2
    path.unlink()


def test_compute_checksum_different_content():
    """Test that different content produces different checksums."""
    with tempfile.NamedTemporaryFile(delete=False) as f1:
        f1.write(b"content 1")
        f1.flush()
        path1 = Path(f1.name)

    with tempfile.NamedTemporaryFile(delete=False) as f2:
        f2.write(b"content 2")
        f2.flush()
        path2 = Path(f2.name)

    checksum1 = compute_checksum(path1)
    checksum2 = compute_checksum(path2)

    assert checksum1 != checksum2
    path1.unlink()
    path2.unlink()


def test_verify_checksum_matches():
    """Test verify_checksum returns True for matching checksum."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content")
        f.flush()
        path = Path(f.name)

    checksum = compute_checksum(path)
    result = verify_checksum(path, checksum)

    assert result is True
    path.unlink()


def test_verify_checksum_mismatch():
    """Test verify_checksum returns False for mismatching checksum."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content")
        f.flush()
        path = Path(f.name)

    result = verify_checksum(path, "0000000000000000")

    assert result is False
    path.unlink()


def test_verify_checksum_file_not_found():
    """Test verify_checksum returns False for non-existent file."""
    result = verify_checksum(Path("/nonexistent/file"), "0000000000000000")
    assert result is False


def test_compute_checksum_dict():
    """Test compute_checksum_dict returns expected keys."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test")
        f.flush()
        path = Path(f.name)

    result = compute_checksum_dict(path)

    assert "checksum" in result
    assert "algorithm" in result
    assert result["algorithm"] == "xxh64"
    assert "size" in result
    assert "mtime" in result
    path.unlink()


def test_compute_checksum_file_not_found():
    """Test compute_checksum raises FileNotFoundError for non-existent file."""
    with pytest.raises(FileNotFoundError):
        compute_checksum(Path("/nonexistent/file"))


def test_unsupported_algorithm():
    """Test compute_checksum raises ValueError for unsupported algorithm."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test")
        f.flush()
        path = Path(f.name)

    with pytest.raises(ValueError) as exc_info:
        compute_checksum(path, algorithm="md5")

    assert "Unsupported algorithm" in str(exc_info.value)
    path.unlink()


def test_verify_checksum_dict():
    """Test verify_checksum_dict with valid dict."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content")
        f.flush()
        path = Path(f.name)

    checksum_dict = compute_checksum_dict(path)
    result = verify_checksum_dict(path, checksum_dict)

    assert result is True
    path.unlink()


def test_verify_checksum_dict_size_mismatch():
    """Test verify_checksum_dict with size mismatch."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content")
        f.flush()
        path = Path(f.name)

    checksum_dict = {
        "checksum": "0000000000000000",
        "algorithm": "xxh64",
        "size": 999,  # Wrong size
    }

    result = verify_checksum_dict(path, checksum_dict)

    assert result is False
    path.unlink()
