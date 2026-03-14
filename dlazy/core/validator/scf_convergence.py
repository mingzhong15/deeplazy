"""SCF convergence validator for OpenMX outputs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from dlazy.core.validator.base import Validator, ValidationResult
from dlazy.core.validator.registry import register_validator


@register_validator("scf_convergence")
class SCFConvergenceValidator(Validator):
    """Validator for SCF convergence in OpenMX outputs.

    Checks if SCF iterations are within acceptable limits.
    """

    validator_type = "scf_convergence"

    def __init__(
        self,
        max_iterations: int = 100,
        convergence_markers: Optional[List[str]] = None,
        fail_markers: Optional[List[str]] = None,
    ):
        """Initialize SCF convergence validator.

        Args:
            max_iterations: Maximum allowed SCF iterations
            convergence_markers: Strings indicating successful convergence
            fail_markers: Strings indicating failure
        """
        self.max_iterations = max_iterations
        self.convergence_markers = convergence_markers or [
            "SCF convergence achieved",
            "convergence achieved",
            "Convergence has been achieved",
        ]
        self.fail_markers = fail_markers or [
            "SCF NOT CONVERGED",
            "not converged",
            "SCF failed to converge",
        ]

    def validate(self, path: Path) -> ValidationResult:
        """Validate SCF convergence.

        Args:
            path: Path to OpenMX output file

        Returns:
            ValidationResult with convergence status
        """
        path = Path(path)

        if not path.exists():
            return ValidationResult(
                is_valid=False,
                errors=[f"File not found: {path}"],
            )

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Failed to read file: {e}"],
            )

        # Parse SCF iterations
        iterations = self._parse_scf_iterations(content)

        # Check for convergence markers
        is_converged = self._check_convergence_markers(content)

        # Check for failure markers
        has_failed = self._check_failure_markers(content)

        errors: List[str] = []
        warnings: List[str] = []

        if has_failed:
            errors.append("SCF convergence failed (failure marker found in output)")
        elif not is_converged:
            if iterations is not None and iterations >= self.max_iterations:
                errors.append(
                    f"SCF did not converge: {iterations} iterations >= max ({self.max_iterations})"
                )
            else:
                warnings.append(
                    f"SCF convergence status unclear: {iterations or 'unknown'} iterations"
                )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details={
                "iterations": iterations,
                "max_iterations": self.max_iterations,
                "has_convergence_marker": is_converged,
                "has_failure_marker": has_failed,
            },
        )

    def _parse_scf_iterations(self, content: str) -> Optional[int]:
        """Parse SCF iteration count from output.

        Args:
            content: OpenMX output content

        Returns:
            Number of SCF iterations or None if not found
        """
        # Common patterns for SCF iterations
        patterns = [
            r"SCF iteration\s+(\d+)",
            r"Iteration\s+(\d+).*energy",
            r"SCF:\s+(\d+)\s+iterations",
            r"(\d+)\s+SCF steps",
        ]

        max_iter = 0
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                for match in matches:
                    try:
                        iter_count = int(match)
                        max_iter = max(max_iter, iter_count)
                    except ValueError:
                        continue

        return max_iter if max_iter > 0 else None

    def _check_convergence_markers(self, content: str) -> bool:
        """Check for convergence success markers.

        Args:
            content: OpenMX output content

        Returns:
            True if convergence marker found
        """
        for marker in self.convergence_markers:
            if marker.lower() in content.lower():
                return True
        return False

    def _check_failure_markers(self, content: str) -> bool:
        """Check for failure markers.

        Args:
            content: OpenMX output content

        Returns:
            True if failure marker found
        """
        for marker in self.fail_markers:
            if marker.lower() in content.lower():
                return True
        return False


def parse_scf_iterations(output_file: Path) -> Optional[int]:
    """Parse SCF iteration count from OpenMX output file.

    Args:
        output_file: Path to OpenMX output file

    Returns:
        Number of SCF iterations or None if not found
    """
    validator = SCFConvergenceValidator()

    if not output_file.exists():
        return None

    try:
        content = output_file.read_text(encoding="utf-8", errors="replace")
        return validator._parse_scf_iterations(content)
    except Exception:
        return None


def check_convergence(output_file: Path, max_iterations: int = 100) -> ValidationResult:
    """Check if SCF converged.

    Args:
        output_file: Path to OpenMX output file
        max_iterations: Maximum allowed iterations

    Returns:
        ValidationResult with convergence status
    """
    validator = SCFConvergenceValidator(max_iterations=max_iterations)
    return validator.validate(output_file)
