# 安全修复快速参考

## 概述

本文档提供安全问题修复的快速参考指南，帮助开发者快速应用安全修复。

## 核心安全函数

### 1. 路径验证 (`validate_path`)

**用途**: 防止路径遍历攻击

**使用示例**:
```python
from dlazy.security import validate_path

# 验证绝对路径
safe_path = validate_path("/data/workflows/file.txt", must_exist=True)

# 验证相对路径(需要基准目录)
safe_path = validate_path("file.txt", base_dir=base_dir, must_exist=True)

# 禁止符号链接
safe_path = validate_path(path, allow_symlinks=False)
```

### 2. 命令安全执行 (`run_command_safe`)

**用途**: 防止命令注入攻击

**使用示例**:
```python
from dlazy.security import run_command_safe

# 安全执行命令
run_command_safe(
    "cp {input} {output}",
    args={
        'input': input_file,
        'output': output_file,
    },
    cwd=work_dir,
    check=True,
)

# 带超时的命令
run_command_safe("long_running_command", timeout=300)
```

### 3. Shell参数转义 (`sanitize_shell_arg`)

**用途**: 安全转义shell参数

**使用示例**:
```python
from dlazy.security import sanitize_shell_arg

safe_arg = sanitize_shell_arg("file with spaces")  # 'file with spaces'
safe_arg = sanitize_shell_arg("file; rm -rf /")    # 'file; rm -rf /'
```

### 4. 文件名清理 (`sanitize_filename`)

**用途**: 清理危险文件名字符

**使用示例**:
```python
from dlazy.security import sanitize_filename

safe_name = sanitize_filename("../../../etc/passwd")  # .._.._.._etc_passwd
safe_name = sanitize_filename("file<>:\"|?*.txt")    # file______.txt
```

## 常见场景修复

### 场景1: 修复命令注入

**修复前**:
```python
command = ctx.config["commands"]["create"].format(poscar=path, scf=scf_path)
subprocess.run(command, shell=True)
```

**修复后**:
```python
from dlazy.security import validate_path, run_command_safe

validated_path = validate_path(path, must_exist=True)
run_command_safe(
    ctx.config["commands"]["create"],
    args={'poscar': validated_path, 'scf': scf_path},
    check=True,
)
```

### 场景2: 修复路径遍历

**修复前**:
```python
config_path = Path(args.config).resolve()
```

**修复后**:
```python
from dlazy.security import validate_path

config_path = validate_path(args.config, must_exist=True)
```

### 场景3: 修复模板注入

**修复前**:
```python
return f"workflow_root = Path('{workflow_root_arg}')"
```

**修复后**:
```python
import shlex
from dlazy.security import validate_path

validated_root = validate_path(workflow_root_arg)
safe_root = shlex.quote(str(validated_root))
return f"workflow_root = Path({safe_root})"
```

## 安全检查清单

- [ ] 所有 `subprocess.run(..., shell=True)` 已替换为 `run_command_safe()`
- [ ] 所有用户输入路径已通过 `validate_path()` 验证
- [ ] 所有shell参数已通过 `sanitize_shell_arg()` 转义
- [ ] 所有文件名已通过 `sanitize_filename()` 清理
- [ ] 配置文件命令模板已通过 `validate_command_template()` 验证
- [ ] 所有测试通过

## 运行安全测试

```bash
# 运行所有安全测试
pytest tests/test_security.py -v

# 运行特定测试
pytest tests/test_security.py::TestShellInjection -v
pytest tests/test_security.py::TestPathValidation -v

# 查看覆盖率
pytest tests/test_security.py --cov=dlazy.security --cov-report=html
```

## 运行安全检查脚本

```bash
./security_check.sh
```

## 紧急问题处理

如果发现安全问题:

1. **立即隔离**: 停止受影响的服务
2. **评估影响**: 确定受影响的系统范围
3. **应用修复**: 按照本指南进行修复
4. **验证修复**: 运行安全测试
5. **文档记录**: 记录问题和解决方案

## 联系方式

安全问题报告: security@example.com

## 更新日志

- 2026-03-13: 初始版本
