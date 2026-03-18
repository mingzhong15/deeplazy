"""Template loader for dlazy job templates."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils.common import load_yaml_config
from .utils.security import validate_command_template
from dlazy.core.exceptions import SecurityError

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"

# Required fields for template validation
REQUIRED_FIELDS = {
    "name": str,
    "slurm": dict,
    "commands": dict,
    "output": dict,
}

# Required slurm fields
SLURM_REQUIRED_FIELDS = [
    "job_name",
    "partition",
    "nodes",
    "ntasks_per_node",
]

# Required output fields
OUTPUT_REQUIRED_FIELDS = [
    "dir",
    "pattern",
]


def _get_logger() -> logging.Logger:
    """Get logger for template loader."""
    return logging.getLogger("dlazy.template_loader")


def list_templates() -> List[str]:
    """List all available template names.

    Returns:
        List of template names (without .yaml extension)
    """
    _get_logger().debug("Scanning template directory: %s", TEMPLATE_DIR)

    if not TEMPLATE_DIR.exists():
        _get_logger().warning("Template directory does not exist: %s", TEMPLATE_DIR)
        return []

    templates = []
    for yaml_file in TEMPLATE_DIR.glob("*.yaml"):
        templates.append(yaml_file.stem)

    _get_logger().debug("Found templates: %s", templates)
    return sorted(templates)


def load_template(name: str, use_cache: bool = True) -> Dict[str, Any]:
    """Load a template by name.

    Args:
        name: Template name (without .yaml extension)
        use_cache: Whether to use cached template if available

    Returns:
        Template configuration dictionary

    Raises:
        FileNotFoundError: If template file does not exist
        ValueError: If template name is invalid
    """
    # Validate template name
    if not name:
        raise ValueError("Template name cannot be empty")

    # Check for path traversal
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError(f"Invalid template name: {name}")

    template_path = TEMPLATE_DIR / f"{name}.yaml"

    if not template_path.exists():
        available = list_templates()
        raise FileNotFoundError(
            f"Template '{name}' not found. Available templates: {available}"
        )

    _get_logger().debug("Loading template: %s from %s", name, template_path)

    config = load_yaml_config(template_path, use_cache=use_cache)

    # Validate required top-level fields
    is_valid, errors = validate_template(config)
    if not is_valid:
        raise ValueError(f"Invalid template '{name}': {errors}")

    return config


def validate_template(template: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate template dictionary has required fields.

    Args:
        template: Template configuration dictionary

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors: List[str] = []

    # Check required top-level fields
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in template:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(template[field], expected_type):
            errors.append(
                f"Field '{field}' should be {expected_type.__name__}, "
                f"got {type(template[field]).__name__}"
            )

    # Check slurm fields
    if "slurm" in template:
        slurm = template["slurm"]
        for field in SLURM_REQUIRED_FIELDS:
            if field not in slurm:
                errors.append(f"Missing required slurm field: {field}")

    # Check output fields
    if "output" in template:
        output = template["output"]
        for field in OUTPUT_REQUIRED_FIELDS:
            if field not in output:
                errors.append(f"Missing required output field: {field}")

    # Check commands is non-empty
    if "commands" in template:
        if not template["commands"]:
            errors.append("commands must be a non-empty dictionary")
        else:
            for cmd_name, cmd_template in template["commands"].items():
                if isinstance(cmd_template, str):
                    try:
                        validate_command_template(cmd_template)
                    except SecurityError as e:
                        errors.append(f"commands.{cmd_name}: {e}")

    is_valid = len(errors) == 0

    if not is_valid:
        _get_logger().warning("Template validation failed: %s", errors)

    return is_valid, errors


def get_template_path(name: str) -> Path:
    """Get the full path to a template file.

    Args:
        name: Template name

    Returns:
        Path to template file
    """
    return TEMPLATE_DIR / f"{name}.yaml"
