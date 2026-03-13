"""安全工具函数 - 防止命令注入、路径遍历、模板注入、配置验证"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dlazy.core.exceptions import SecurityError


def validate_path(
    path: Union[str, Path],
    base_dir: Optional[Path] = None,
    allow_symlinks: bool = True,
    must_exist: bool = False,
) -> Path:
    """验证路径安全性，防止路径遍历攻击

    Args:
        path: 待验证路径
        base_dir: 基准目录(可选)，路径必须在此目录内
        allow_symlinks: 是否允许符号链接
        must_exist: 路径是否必须存在

    Returns:
        解析后的绝对路径

    Raises:
        SecurityError: 路径验证失败
        FileNotFoundError: 路径不存在(当must_exist=True)
    """
    try:
        path_obj = Path(path)

        if not path_obj.is_absolute():
            if base_dir is None:
                base_dir = Path.cwd()
            path_obj = (base_dir / path_obj).resolve()
        else:
            path_obj = path_obj.resolve()

        if not allow_symlinks and path_obj.is_symlink():
            raise SecurityError(f"符号链接不被允许: {path_obj}")

        if base_dir is not None:
            base_resolved = base_dir.resolve()
            try:
                path_obj.relative_to(base_resolved)
            except ValueError:
                raise SecurityError(
                    f"路径遍历攻击检测: {path_obj} 不在基准目录 {base_resolved} 内"
                )

        if must_exist and not path_obj.exists():
            raise FileNotFoundError(f"路径不存在: {path_obj}")

        path_str = str(path_obj)
        dangerous_patterns = [
            r"\.\.",
            r"/etc/passwd",
            r"/etc/shadow",
            r"/root/",
            r"\.ssh/",
            r"\.gnupg/",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, path_str):
                raise SecurityError(f"检测到危险路径模式: {path_obj}")

        return path_obj

    except SecurityError:
        raise
    except Exception as e:
        raise SecurityError(f"路径验证失败: {path}, 错误: {e}")


def sanitize_shell_arg(arg: Union[str, Path, int, float]) -> str:
    """安全转义shell参数，防止命令注入"""
    if isinstance(arg, Path):
        arg = str(arg)
    elif isinstance(arg, (int, float)):
        return str(arg)

    if not isinstance(arg, str):
        raise SecurityError(f"不支持的参数类型: {type(arg)}")

    return shlex.quote(arg)


def safe_format_command(template: str, **kwargs) -> str:
    """安全格式化命令模板，防止命令注入"""
    safe_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, (str, Path)):
            safe_kwargs[key] = sanitize_shell_arg(value)
        else:
            safe_kwargs[key] = str(value)

    try:
        return template.format(**safe_kwargs)
    except KeyError as e:
        raise SecurityError(f"模板参数缺失: {e}")


def run_command_safe(
    command_template: str,
    args: Optional[Dict[str, Any]] = None,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture_output: bool = False,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    """安全执行shell命令"""
    args = args or {}

    if cwd is not None:
        cwd = validate_path(cwd, must_exist=True)

    safe_command = safe_format_command(command_template, **args)

    try:
        result = subprocess.run(
            safe_command,
            shell=True,
            cwd=str(cwd) if cwd else None,
            env=env,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        raise
    except subprocess.CalledProcessError:
        raise
    except Exception as e:
        raise SecurityError(f"命令执行失败: {e}")


def validate_template_string(template: str) -> bool:
    """验证模板字符串是否安全"""
    dangerous_patterns = [
        r"__import__",
        r"eval\s*\(",
        r"exec\s*\(",
        r"compile\s*\(",
        r"open\s*\(",
        r"os\.system",
        r"subprocess\.",
        r"importlib",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, template, re.IGNORECASE):
            raise SecurityError(f"模板包含危险代码模式: {pattern}")

    return True


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除危险字符"""
    filename = filename.replace("/", "_").replace("\\", "_")

    dangerous_chars = ["<", ">", ":", '"', "|", "?", "*", "\0"]
    for char in dangerous_chars:
        filename = filename.replace(char, "_")

    filename = filename.lstrip(". ")

    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext

    return filename or "unnamed"


def validate_command_template(template: str) -> bool:
    """验证命令模板是否安全"""
    dangerous_commands = [
        r"rm\s+-rf",
        r"dd\s+if=",
        r"mkfs",
        r"fdisk",
        r"chmod\s+777",
        r"chown\s+root",
        r">\s*/etc/",
        r"wget\s+",
        r"curl\s+.*\|",
    ]

    for pattern in dangerous_commands:
        if re.search(pattern, template, re.IGNORECASE):
            raise SecurityError(f"命令模板包含危险命令: {pattern}")

    return True


def validate_config_section(section: Dict[str, Any], section_name: str) -> List[str]:
    """验证配置段的安全性"""
    warnings = []

    if "commands" in section:
        for cmd_name, cmd_template in section["commands"].items():
            try:
                if isinstance(cmd_template, str):
                    validate_command_template(cmd_template)
            except SecurityError as e:
                warnings.append(f"[{section_name}] {cmd_name}: {e}")

    path_keys = ["model_dir", "output_dir", "input_dir"]
    for key in path_keys:
        if key in section:
            try:
                validate_path(section[key])
            except SecurityError as e:
                warnings.append(f"[{section_name}] {key}: {e}")

    return warnings


def validate_global_config(config: Dict[str, Any]) -> List[str]:
    """验证全局配置的安全性"""
    warnings = []

    sections = ["0olp", "1infer", "2calc"]
    for section_name in sections:
        if section_name in config:
            section_warnings = validate_config_section(
                config[section_name], section_name
            )
            warnings.extend(section_warnings)

    if "software" in config:
        software = config["software"]
        for key, value in software.items():
            if isinstance(value, str) and ("/" in value or "\\" in value):
                try:
                    validate_path(value)
                except SecurityError as e:
                    warnings.append(f"[software] {key}: {e}")

    return warnings
