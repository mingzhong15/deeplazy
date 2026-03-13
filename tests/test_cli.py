#!/usr/bin/env python3
"""测试 CLI 功能"""

import subprocess
import sys
from pathlib import Path


def test_version():
    """测试版本命令"""
    result = subprocess.run(
        [sys.executable, "-m", "dlazy", "version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "2.9.7" in result.stdout
    print("✓ test_version passed")


def test_help():
    """测试帮助命令"""
    result = subprocess.run(
        [sys.executable, "-m", "dlazy", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()
    print("✓ test_help passed")


def test_validate_config():
    """测试配置验证"""
    config_path = (
        Path(__file__).parent.parent
        / "examples"
        / "demo-workflow"
        / "global_config.yaml"
    )

    if not config_path.exists():
        print("✗ test_validate_config skipped (config not found)")
        return

    result = subprocess.run(
        [sys.executable, "-m", "dlazy", "validate", "--config", str(config_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "验证通过" in result.stdout
    print("✓ test_validate_config passed")


def test_import():
    """测试导入"""
    from dlazy import __version__, WorkflowExecutor

    assert __version__ == "2.9.7"
    assert WorkflowExecutor is not None
    print("✓ test_import passed")


if __name__ == "__main__":
    test_import()
    test_version()
    test_help()
    test_validate_config()
    print("\n所有测试通过!")
