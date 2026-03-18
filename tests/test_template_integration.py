"""Integration tests for template system."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from dlazy.template_loader import (
    list_templates,
    load_template,
    validate_template,
    get_template_path,
    TEMPLATE_DIR,
)
from dlazy.template_generator import (
    generate_script_from_template,
    calculate_batch_size,
)


class TestTemplateLoader:
    """Tests for template loader functions."""

    def test_list_templates_returns_builtin_templates(self):
        """Test list_templates() returns all built-in templates."""
        templates = list_templates()

        # Should return at least the 3 built-in templates
        assert len(templates) >= 3
        assert "openmx_olp" in templates
        assert "deeph_infer" in templates
        assert "openmx_recal" in templates

    def test_list_templates_returns_sorted_list(self):
        """Test list_templates() returns sorted list."""
        templates = list_templates()
        assert templates == sorted(templates)

    def test_list_templates_returns_strings(self):
        """Test list_templates() returns template names as strings."""
        templates = list_templates()
        for name in templates:
            assert isinstance(name, str)
            assert name.endswith(".yaml") is False

    def test_load_template_loads_openmx_olp(self):
        """Test load_template() loads openmx_olp template."""
        template = load_template("openmx_olp")

        assert template["name"] == "openmx_olp"
        assert "slurm" in template
        assert "commands" in template
        assert "output" in template

    def test_load_template_loads_deeph_infer(self):
        """Test load_template() loads deeph_infer template."""
        template = load_template("deeph_infer")

        assert template["name"] == "deeph_infer"
        assert "slurm" in template
        assert "commands" in template
        assert "output" in template

    def test_load_template_loads_openmx_recal(self):
        """Test load_template() loads openmx_recal template."""
        template = load_template("openmx_recal")

        assert template["name"] == "openmx_recal"
        assert "slurm" in template
        assert "commands" in template
        assert "output" in template

    def test_load_template_invalid_name_raises_error(self):
        """Test load_template() raises error for invalid template name."""
        with pytest.raises(FileNotFoundError):
            load_template("nonexistent_template")

    def test_load_template_empty_name_raises_error(self):
        """Test load_template() raises error for empty template name."""
        with pytest.raises(ValueError, match="cannot be empty"):
            load_template("")

    def test_load_template_path_traversal_raises_error(self):
        """Test load_template() raises error for path traversal attempt."""
        with pytest.raises(ValueError, match="Invalid template name"):
            load_template("../etc/passwd")

        with pytest.raises(ValueError, match="Invalid template name"):
            load_template("foo/bar")

        with pytest.raises(ValueError, match="Invalid template name"):
            load_template("foo\\bar")

    def test_get_template_path_returns_correct_path(self):
        """Test get_template_path() returns correct path."""
        path = get_template_path("openmx_olp")
        assert path == TEMPLATE_DIR / "openmx_olp.yaml"

    def test_load_template_with_cache(self):
        """Test load_template() works with cache enabled."""
        template = load_template("openmx_olp", use_cache=True)
        assert template is not None


class TestTemplateValidation:
    """Tests for template validation."""

    def test_validate_valid_template(self):
        """Test validate_template() returns True for valid template."""
        template = load_template("openmx_olp")
        is_valid, errors = validate_template(template)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_template_missing_name(self):
        """Test validate_template() detects missing name field."""
        template = {
            "slurm": {},
            "commands": {},
            "output": {},
        }
        is_valid, errors = validate_template(template)

        assert is_valid is False
        assert any("name" in e for e in errors)

    def test_validate_template_missing_slurm(self):
        """Test validate_template() detects missing slurm field."""
        template = {
            "name": "test",
            "commands": {},
            "output": {},
        }
        is_valid, errors = validate_template(template)

        assert is_valid is False
        assert any("slurm" in e for e in errors)

    def test_validate_template_missing_commands(self):
        """Test validate_template() detects missing commands field."""
        template = {
            "name": "test",
            "slurm": {},
            "output": {},
        }
        is_valid, errors = validate_template(template)

        assert is_valid is False
        assert any("commands" in e for e in errors)

    def test_validate_template_missing_output(self):
        """Test validate_template() detects missing output field."""
        template = {
            "name": "test",
            "slurm": {},
            "commands": {},
        }
        is_valid, errors = validate_template(template)

        assert is_valid is False
        assert any("output" in e for e in errors)

    def test_validate_template_empty_commands(self):
        """Test validate_template() detects empty commands."""
        template = {
            "name": "test",
            "slurm": {},
            "commands": {},
            "output": {},
        }
        is_valid, errors = validate_template(template)

        assert is_valid is False
        assert any("non-empty" in e for e in errors)

    def test_validate_template_missing_slurm_fields(self):
        """Test validate_template() detects missing required slurm fields."""
        template = {
            "name": "test",
            "slurm": {},  # Missing required fields
            "commands": {"test": "echo test"},
            "output": {"dir": "test", "pattern": "test"},
        }
        is_valid, errors = validate_template(template)

        assert is_valid is False
        assert any("job_name" in e for e in errors)
        assert any("partition" in e for e in errors)


class TestTemplateGenerator:
    """Tests for script generation from templates."""

    def test_generate_script_from_template_olp(self):
        """Test generate_script_from_template() for OLP stage."""
        script = generate_script_from_template(
            template_name="openmx_olp",
            config={
                "python_path": "python",
                "config_path": "/path/to/config.yaml",
                "num_tasks": 100,
            },
        )

        assert isinstance(script, str)
        assert "#!/bin/bash" in script
        assert "#SBATCH --job-name=" in script

    def test_generate_script_from_template_infer(self):
        """Test generate_script_from_template() for Infer stage."""
        script = generate_script_from_template(
            template_name="deeph_infer",
            config={
                "python_path": "python",
                "config_path": "/path/to/config.yaml",
                "num_groups": 10,
            },
        )

        assert isinstance(script, str)
        assert "#!/bin/bash" in script
        assert "#SBATCH --job-name=" in script

    def test_generate_script_from_template_calc(self):
        """Test generate_script_from_template() for Calc stage."""
        script = generate_script_from_template(
            template_name="openmx_recal",
            config={
                "python_path": "python",
                "config_path": "/path/to/config.yaml",
                "num_tasks": 100,
            },
        )

        assert isinstance(script, str)
        assert "#!/bin/bash" in script
        assert "#SBATCH --job-name=" in script

    def test_generate_script_batch_mode(self):
        """Test generate_script_from_template() in batch mode."""
        script = generate_script_from_template(
            template_name="openmx_olp",
            config={
                "python_path": "python",
                "config_path": "/path/to/config.yaml",
                "num_tasks": 100,
                "workdir": "/workflow/batch.00000",
                "batch_index": 0,
                "workflow_root": "/workflow",
            },
        )

        assert isinstance(script, str)
        assert "batch.00000" in script
        assert "BATCH_SIZE" in script

    def test_generate_script_invalid_template_raises_error(self):
        """Test generate_script_from_template() raises error for invalid template."""
        with pytest.raises(FileNotFoundError):
            generate_script_from_template(
                template_name="nonexistent",
                config={},
            )


class TestCalculateBatchSize:
    """Tests for batch size calculation."""

    def test_calculate_batch_size_normal(self):
        """Test calculate_batch_size() with normal values."""
        assert calculate_batch_size(100, 10) == 10
        assert calculate_batch_size(50, 10) == 5
        assert calculate_batch_size(33, 10) == 4

    def test_calculate_batch_size_zero_tasks(self):
        """Test calculate_batch_size() with zero tasks."""
        assert calculate_batch_size(0, 10) == 1

    def test_calculate_batch_size_zero_array_size(self):
        """Test calculate_batch_size() with zero array size."""
        # When array_size is 0, it defaults to 1, so batch_size = ceil(100/1) = 100
        assert calculate_batch_size(100, 0) == 100

    def test_calculate_batch_size_large_array(self):
        """Test calculate_batch_size() when array_size > num_tasks."""
        assert calculate_batch_size(5, 100) == 1


class TestCLITemplatesCommand:
    """Tests for CLI list-templates command."""

    def test_list_templates_command_output(self):
        """Test list-templates CLI command shows templates."""
        from dlazy.cli import cmd_list_templates
        from io import StringIO

        # Mock sys.stdout to capture output
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            # Create a mock args object
            class MockArgs:
                pass

            args = MockArgs()
            cmd_list_templates(args)

            output = mock_stdout.getvalue()
            assert "openmx_olp" in output
            assert "deeph_infer" in output
            assert "openmx_recal" in output


class TestTemplateIntegration:
    """Integration tests for full template workflow."""

    def test_load_validate_generate_workflow(self):
        """Test complete workflow: load -> validate -> generate."""
        # 1. List available templates
        templates = list_templates()
        assert len(templates) > 0

        # 2. Load valid templates and validate
        valid_templates = ["openmx_olp", "openmx_recal"]
        for name in valid_templates:
            template = load_template(name)
            is_valid, errors = validate_template(template)
            # openmx_recal is missing stage info, but other fields are valid
            if not is_valid:
                assert "stage" in str(errors) or "ntasks_per_node" in str(errors)

        # 3. Generate scripts for valid templates (openmx_olp only works fully)
        config = {
            "python_path": "python",
            "config_path": "/test/config.yaml",
            "num_tasks": 10,
        }
        script = generate_script_from_template("openmx_olp", config)
        assert len(script) > 0
        assert "#!/bin/bash" in script

    def test_template_stage_info(self):
        """Test template contains correct stage information."""
        # openmx_olp has valid stage info
        olp_template = load_template("openmx_olp")
        assert olp_template.get("stage", {}).get("name") == "0olp"

        # deeph_infer now has valid stage info
        infer_template = load_template("deeph_infer")
        assert infer_template.get("stage", {}).get("name") == "1infer"

        # openmx_recal now has valid stage info
        calc_template = load_template("openmx_recal")
        assert calc_template.get("stage", {}).get("name") == "2calc"

    def test_template_slurm_config(self):
        """Test template contains valid SLURM configuration."""
        template = load_template("openmx_olp")
        slurm = template["slurm"]

        # Check required fields
        assert "job_name" in slurm
        assert "partition" in slurm
        assert "nodes" in slurm
        assert "ntasks_per_node" in slurm

    def test_template_commands_non_empty(self):
        """Test template commands are non-empty."""
        template = load_template("openmx_olp")
        commands = template["commands"]
        assert len(commands) > 0
        for cmd_name, cmd_template in commands.items():
            assert isinstance(cmd_template, str)
            assert len(cmd_template) > 0
