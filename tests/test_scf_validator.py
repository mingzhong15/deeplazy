"""Tests for SCF convergence validator."""

import pytest

from dlazy.core.validator.base import ValidationResult
from dlazy.core.validator.scf_convergence import (
    SCFConvergenceValidator,
    check_convergence,
    parse_scf_iterations,
)


class TestSCFConvergenceValidator:
    """Tests for SCFConvergenceValidator."""

    def test_validate_converged_output(self, tmp_path):
        output = tmp_path / "output.txt"
        output.write_text("""
Some header
SCF iteration 1 energy: -100.5
SCF iteration 2 energy: -100.8
SCF convergence achieved
Final energy: -100.8
""")
        validator = SCFConvergenceValidator()
        result = validator.validate(output)

        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_not_converged(self, tmp_path):
        output = tmp_path / "output.txt"
        output.write_text("""
SCF iteration 1 energy: -100.5
SCF iteration 2 energy: -100.8
SCF NOT CONVERGED
""")
        validator = SCFConvergenceValidator()
        result = validator.validate(output)

        assert not result.is_valid
        assert len(result.errors) == 1
        assert "failed" in result.errors[0].lower()

    def test_validate_max_iterations_exceeded(self, tmp_path):
        output = tmp_path / "output.txt"
        lines = [f"SCF iteration {i} energy: -100.{i}" for i in range(1, 105)]
        output.write_text("\n".join(lines))

        validator = SCFConvergenceValidator(max_iterations=100)
        result = validator.validate(output)

        assert not result.is_valid
        assert any("iteration" in e.lower() for e in result.errors)

    def test_validate_file_not_found(self, tmp_path):
        output = tmp_path / "nonexistent.txt"
        validator = SCFConvergenceValidator()
        result = validator.validate(output)

        assert not result.is_valid
        assert "not found" in result.errors[0].lower()

    def test_parse_scf_iterations(self, tmp_path):
        output = tmp_path / "output.txt"
        output.write_text("""
SCF iteration 1 energy: -100.0
SCF iteration 2 energy: -100.5
SCF iteration 3 energy: -100.8
""")
        iterations = parse_scf_iterations(output)
        assert iterations == 3

    def test_parse_scf_iterations_not_found(self, tmp_path):
        output = tmp_path / "output.txt"
        output.write_text("No SCF data here")
        iterations = parse_scf_iterations(output)
        assert iterations is None

    def test_check_convergence(self, tmp_path):
        output = tmp_path / "output.txt"
        output.write_text("""
SCF iteration 50
SCF convergence achieved
""")
        result = check_convergence(output, max_iterations=100)
        assert result.is_valid

    def test_check_convergence_failed(self, tmp_path):
        output = tmp_path / "output.txt"
        output.write_text("""
SCF iteration 150
""")
        result = check_convergence(output, max_iterations=100)
        assert not result.is_valid

    def test_custom_markers(self, tmp_path):
        output = tmp_path / "output.txt"
        output.write_text("""
Custom convergence marker here
""")
        validator = SCFConvergenceValidator(
            convergence_markers=["Custom convergence marker"]
        )
        result = validator.validate(output)
        assert result.is_valid

    def test_failure_marker_overrides_convergence(self, tmp_path):
        output = tmp_path / "output.txt"
        output.write_text("""
SCF convergence achieved
SCF NOT CONVERGED (error occurred)
""")
        validator = SCFConvergenceValidator()
        result = validator.validate(output)

        assert not result.is_valid
