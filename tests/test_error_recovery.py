"""Tests for batch workflow error recovery mechanism."""

import json
import tempfile
from pathlib import Path
from dlazy.core.workflow_state import ErrorContext, record_error
from dlazy.core import ErrorTask
from dlazy.core.tasks import _read_jsonl
from dlazy.path_resolver import BatchPathResolver


def test_error_context_creation():
    """Test ErrorContext dataclass."""
    ctx = ErrorContext(
        path="/path/to/POSCAR",
        stage="olp",
        error="Test error",
        batch_index=0,
        task_id="000001",
        resolver=None,
    )
    assert ctx.path == "/path/to/POSCAR"
    assert ctx.stage == "olp"
    assert ctx.error == "Test error"


def test_record_error_olp():
    """Test recording OLP stage error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_root = Path(tmpdir)
        resolver = BatchPathResolver(workflow_root, 0)

        ctx = ErrorContext(
            path="/path/to/POSCAR",
            stage="olp",
            error="OLP calculation failed",
            batch_index=0,
            task_id="000001",
            resolver=resolver,
        )

        record_error(ctx)

        # Check error file was created
        error_file = resolver.get_olp_error_file()
        assert error_file.exists(), f"Error file not created: {error_file}"

        # Check error record format
        errors = list(_read_jsonl(error_file))
        assert len(errors) == 1
        assert errors[0]["path"] == "/path/to/POSCAR"
        assert errors[0]["stage"] == "olp"
        assert errors[0]["error"] == "OLP calculation failed"
        assert errors[0]["batch_id"] == "0"
        assert errors[0]["task_id"] == "000001"


def test_record_error_infer():
    """Test recording Infer stage error (group failure)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_root = Path(tmpdir)
        resolver = BatchPathResolver(workflow_root, 0)

        # Simulate group failure with multiple tasks
        for i in range(3):
            ctx = ErrorContext(
                path=f"/path/to/POSCAR_{i}",
                stage="infer",
                error="Group 1 failed: Transform error",
                batch_index=0,
                task_id=f"g001_t{i:06d}",
                resolver=resolver,
            )
            record_error(ctx)

        # Check error file
        error_file = resolver.get_infer_error_file()
        assert error_file.exists()

        errors = list(_read_jsonl(error_file))
        assert len(errors) == 3
        for i, err in enumerate(errors):
            assert err["stage"] == "infer"
            assert "Group 1 failed" in err["error"]


def test_record_error_calc():
    """Test recording Calc stage error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_root = Path(tmpdir)
        resolver = BatchPathResolver(workflow_root, 0)

        ctx = ErrorContext(
            path="/path/to/POSCAR",
            stage="calc",
            error="SCF not converged",
            batch_index=0,
            task_id="000001",
            resolver=resolver,
        )

        record_error(ctx)

        error_file = resolver.get_calc_error_file()
        assert error_file.exists()

        errors = list(_read_jsonl(error_file))
        assert len(errors) == 1
        assert errors[0]["stage"] == "calc"
        assert "SCF not converged" in errors[0]["error"]


def test_error_jsonl_format():
    """Test that error records are valid JSON Lines."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_root = Path(tmpdir)
        resolver = BatchPathResolver(workflow_root, 0)

        ctx = ErrorContext(
            path="/path/to/POSCAR",
            stage="olp",
            error='Test error with special chars: \n\t"quotes"',
            batch_index=0,
            task_id="000001",
            resolver=resolver,
        )

        record_error(ctx)

        error_file = resolver.get_olp_error_file()

        # Verify it's valid JSONL (each line is valid JSON)
        with open(error_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)  # Should not raise
                    assert "path" in data
                    assert "stage" in data
                    assert "error" in data


def test_multiple_errors_append():
    """Test that multiple errors are appended to the same file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workflow_root = Path(tmpdir)
        resolver = BatchPathResolver(workflow_root, 0)

        for i in range(5):
            ctx = ErrorContext(
                path=f"/path/to/POSCAR_{i}",
                stage="olp",
                error=f"Error {i}",
                batch_index=0,
                task_id=f"{i:06d}",
                resolver=resolver,
            )
            record_error(ctx)

        error_file = resolver.get_olp_error_file()
        errors = list(_read_jsonl(error_file))
        assert len(errors) == 5
