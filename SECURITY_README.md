# 安全修复方案

## 文件清单

本安全修复方案包含以下文件:

### 核心模块
- `dlazy/security.py` - 安全工具函数模块
- `dlazy/config_validator.py` - 配置文件验证模块

### 测试文件
- `tests/test_security.py` - 安全功能单元测试

### 文档
- `SECURITY_FIX_PLAN.md` - 详细的安全修复方案文档
- `SECURITY_QUICK_REFERENCE.md` - 安全修复快速参考指南
- `security_check.sh` - 安全检查脚本

## 快速开始

### 1. 查看详细修复方案

```bash
# 查看完整的安全修复方案文档
cat SECURITY_FIX_PLAN.md

# 或使用 less 浏览
less SECURITY_FIX_PLAN.md
```

### 2. 查看快速参考

```bash
# 查看快速参考指南
cat SECURITY_QUICK_REFERENCE.md
```

### 3. 运行安全测试

```bash
# 安装测试依赖
pip install pytest pytest-cov

# 运行所有安全测试
pytest tests/test_security.py -v

# 查看测试覆盖率
pytest tests/test_security.py --cov=dlazy.security --cov-report=html
```

### 4. 运行安全检查

```bash
# 运行安全检查脚本
./security_check.sh
```

## 修复的问题

### 1. 命令注入漏洞 (严重)
- **位置**: `commands.py` 多处
- **修复**: 使用 `run_command_safe()` 替代 `subprocess.run(..., shell=True)`
- **详见**: `SECURITY_FIX_PLAN.md` 第一章

### 2. 路径遍历漏洞 (严重)
- **位置**: `cli.py` 多处
- **修复**: 使用 `validate_path()` 验证所有路径
- **详见**: `SECURITY_FIX_PLAN.md` 第二章

### 3. 模板注入漏洞 (高)
- **位置**: `template_generator.py`
- **修复**: 使用 `shlex.quote()` 安全转义路径
- **详见**: `SECURITY_FIX_PLAN.md` 第三章

## 核心安全函数

### validate_path()
验证路径安全性,防止路径遍历攻击

```python
from dlazy.security import validate_path

safe_path = validate_path(
    user_input_path,
    base_dir=expected_base_dir,
    must_exist=True,
    allow_symlinks=False
)
```

### run_command_safe()
安全执行shell命令,防止命令注入

```python
from dlazy.security import run_command_safe

run_command_safe(
    "cp {input} {output}",
    args={'input': input_file, 'output': output_file},
    check=True
)
```

### sanitize_shell_arg()
安全转义shell参数

```python
from dlazy.security import sanitize_shell_arg

safe_arg = sanitize_shell_arg("file with spaces; rm -rf /")
```

## 实施步骤

详见 `SECURITY_FIX_PLAN.md` 第六节,建议的实施顺序:

1. **第一阶段**: 创建安全基础设施 (1-2天)
2. **第二阶段**: 修复命令注入漏洞 (2-3天)
3. **第三阶段**: 修复路径遍历漏洞 (1-2天)
4. **第四阶段**: 修复模板注入漏洞 (2-3天)
5. **第五阶段**: 集成测试和验证 (2-3天)

## 测试覆盖

测试文件 `tests/test_security.py` 包含以下测试类:

- `TestPathValidation` - 路径验证测试
- `TestShellInjection` - Shell注入测试
- `TestTemplateInjection` - 模板注入测试
- `TestFilenameSanitization` - 文件名清理测试
- `TestConfigValidation` - 配置验证测试
- `TestIntegrationSecurity` - 集成安全测试

运行所有测试:

```bash
pytest tests/test_security.py -v
```

## 安全最佳实践

1. **最小权限原则** - 使用专用用户运行工作流
2. **输入验证** - 永远不要信任用户输入
3. **白名单机制** - 使用白名单而非黑名单
4. **错误处理** - 不要泄露敏感信息
5. **审计日志** - 记录所有安全相关事件

## 安全检查清单

使用以下清单验证修复完整性:

- [ ] 所有 `subprocess.run(..., shell=True)` 已替换为 `run_command_safe()`
- [ ] 所有用户输入路径已通过 `validate_path()` 验证
- [ ] 所有shell参数已通过 `sanitize_shell_arg()` 转义
- [ ] 所有文件名已通过 `sanitize_filename()` 清理
- [ ] 配置文件命令模板已通过 `validate_command_template()` 验证
- [ ] 所有测试通过
- [ ] 安全检查脚本运行通过

## 参考资料

- OWASP Command Injection: https://owasp.org/www-community/attacks/Command_Injection
- CWE-78: OS Command Injection: https://cwe.mitre.org/data/definitions/78.html
- CWE-22: Path Traversal: https://cwe.mitre.org/data/definitions/22.html
- Python Security Best Practices: https://python.readthedocs.io/en/stable/library/security_warnings.html

## 更新日志

- **2026-03-13**: 初始版本,包含完整的安全修复方案

## 联系方式

如有安全问题或疑问,请联系: security@example.com
