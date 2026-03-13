# 安全修复方案实施摘要

## 已完成工作

### 1. 创建的文件

#### 核心模块 (共2个文件)
- ✅ `dlazy/security.py` (6.3K) - 安全工具函数模块
  - `validate_path()` - 路径验证,防止路径遍历
  - `sanitize_shell_arg()` - Shell参数转义
  - `safe_format_command()` - 安全命令格式化
  - `run_command_safe()` - 安全命令执行
  - `validate_template_string()` - 模板字符串验证
  - `sanitize_filename()` - 文件名清理

- ✅ `dlazy/config_validator.py` (3.1K) - 配置文件验证模块
  - `validate_command_template()` - 命令模板验证
  - `validate_config_section()` - 配置段验证
  - `validate_global_config()` - 全局配置验证

#### 测试文件 (共1个文件)
- ✅ `tests/test_security.py` (7.7K) - 安全功能测试套件
  - `TestPathValidation` - 路径验证测试 (5个测试)
  - `TestShellInjection` - Shell注入测试 (6个测试)
  - `TestTemplateInjection` - 模板注入测试 (3个测试)
  - `TestFilenameSanitization` - 文件名清理测试 (5个测试)
  - `TestConfigValidation` - 配置验证测试 (3个测试)
  - `TestIntegrationSecurity` - 集成测试 (2个测试)
  - **总计: 24个测试用例**

#### 文档文件 (共4个文件)
- ✅ `SECURITY_FIX_PLAN.md` (34K) - 详细的安全修复方案
- ✅ `SECURITY_QUICK_REFERENCE.md` (3.8K) - 快速参考指南
- ✅ `SECURITY_README.md` (4.3K) - 安全修复README
- ✅ `security_check.sh` (1.6K) - 安全检查脚本

**总计: 8个文件, 约64KB**

---

## 安全漏洞分析

### 1. 命令注入漏洞 (严重)
- **发现位置**: 
  - `commands.py:133-137` - OLP阶段
  - `commands.py:260` - Batch模式
  - `commands.py:841-842` - Calc阶段
- **根本原因**: 用户可控路径直接传入 `shell=True` 的 `subprocess.run()`
- **修复方案**: 使用 `run_command_safe()` 替代所有危险的命令执行

### 2. 路径遍历漏洞 (严重)
- **发现位置**: 
  - `cli.py:18-19` - 配置文件路径解析
  - `cli.py:154-155` - 批处理路径解析
- **根本原因**: 未验证路径是否在预期目录内
- **修复方案**: 使用 `validate_path()` 验证所有用户输入的路径

### 3. 模板注入漏洞 (高)
- **发现位置**: 
  - `template_generator.py:130-184` - OLP脚本生成
- **根本原因**: 路径直接嵌入Python代码,特殊字符可导致代码注入
- **修复方案**: 使用 `shlex.quote()` 或环境变量传递路径

---

## 核心功能说明

### 安全工具函数 (`dlazy/security.py`)

#### 1. validate_path() - 路径验证
```python
from dlazy.security import validate_path

# 验证绝对路径
safe_path = validate_path("/data/workflows/file.txt", must_exist=True)

# 验证相对路径(需要基准目录)
safe_path = validate_path("file.txt", base_dir=base_dir, must_exist=True)

# 禁止符号链接
safe_path = validate_path(path, allow_symlinks=False)
```

**功能**:
- 防止路径遍历攻击 (`../../../etc/passwd`)
- 检测危险路径模式 (`/etc/passwd`, `/root/`, `/.ssh/`)
- 验证路径在基准目录内
- 检查符号链接

#### 2. run_command_safe() - 安全命令执行
```python
from dlazy.security import run_command_safe

run_command_safe(
    "cp {input} {output}",
    args={'input': input_file, 'output': output_file},
    check=True
)
```

**功能**:
- 防止命令注入攻击
- 自动转义所有参数
- 支持命令超时
- 支持工作目录验证

#### 3. sanitize_shell_arg() - Shell参数转义
```python
from dlazy.security import sanitize_shell_arg

safe_arg = sanitize_shell_arg("file; rm -rf /")  # 'file; rm -rf /'
```

**功能**:
- 使用 `shlex.quote()` 进行安全转义
- 支持字符串、路径、数字类型

#### 4. sanitize_filename() - 文件名清理
```python
from dlazy.security import sanitize_filename

safe_name = sanitize_filename("../../../etc/passwd")  # .._.._.._etc_passwd
```

**功能**:
- 移除路径分隔符
- 移除危险字符 (`<>:"|?*`)
- 防止隐藏文件 (去除开头的点)
- 限制文件名长度 (≤255字符)

---

## 测试覆盖

### 测试统计
- **测试文件**: 1个
- **测试类**: 6个
- **测试用例**: 24个
- **覆盖率**: 目标 >80%

### 测试类别

#### TestPathValidation (5个测试)
- ✅ 有效绝对路径测试
- ✅ 有效相对路径测试
- ✅ 路径遍历攻击检测测试
- ✅ 符号链接检测测试
- ✅ 危险路径模式检测测试

#### TestShellInjection (6个测试)
- ✅ 简单字符串转义测试
- ✅ 包含空格的字符串测试
- ✅ 注入攻击防护测试
- ✅ 安全命令格式化测试
- ✅ 注入攻击防护测试
- ✅ 安全命令执行测试

#### TestTemplateInjection (3个测试)
- ✅ 有效模板测试
- ✅ 未授权占位符检测测试
- ✅ 危险命令模式检测测试

#### TestFilenameSanitization (5个测试)
- ✅ 正常文件名测试
- ✅ 路径遍历字符清理测试
- ✅ 危险字符清理测试
- ✅ 隐藏文件名清理测试
- ✅ 长文件名截断测试

#### TestConfigValidation (3个测试)
- ✅ 有效配置测试
- ✅ 危险命令配置测试
- ✅ 未授权占位符配置测试

#### TestIntegrationSecurity (2个测试)
- ✅ 端到端命令执行测试
- ✅ 工作流注入防护测试

---

## 下一步行动计划

### 第一阶段: 创建安全基础设施 (1-2天) ✅ **已完成**
- ✅ 实现 `dlazy/security.py` 模块
- ✅ 添加 `SecurityError` 异常类
- ✅ 实现配置验证模块
- ✅ 编写单元测试

### 第二阶段: 修复命令注入漏洞 (2-3天) 📋 **待实施**
**需要修改的文件**:
1. `dlazy/commands.py`
   - 第133-137行: OLP阶段命令执行
   - 第260行: Batch模式命令执行
   - 第841-842行: Calc阶段命令执行
   - 其他 `subprocess.run(..., shell=True)` 调用

**修改示例**:
```python
# 修复前
command_create = ctx.config["commands"]["create_infile"].format(
    poscar=path, scf=scf_path
)
subprocess.run(command_create, shell=True)

# 修复后
from dlazy.security import validate_path, run_command_safe

validated_path = validate_path(path, must_exist=True)
run_command_safe(
    ctx.config["commands"]["create_infile"],
    args={'poscar': validated_path, 'scf': scf_path},
    check=True
)
```

### 第三阶段: 修复路径遍历漏洞 (1-2天) 📋 **待实施**
**需要修改的文件**:
1. `dlazy/cli.py`
   - 第18-19行: 配置文件路径解析
   - 第154-155行: 批处理路径解析
   - 其他路径解析位置

**修改示例**:
```python
# 修复前
config_path = Path(args.config).resolve()

# 修复后
from dlazy.security import validate_path

config_path = validate_path(args.config, must_exist=True)
```

### 第四阶段: 修复模板注入漏洞 (2-3天) 📋 **待实施**
**需要修改的文件**:
1. `dlazy/template_generator.py`
   - 第130-184行: OLP脚本生成
   - 类似问题在infer/calc脚本生成中

**修改方案**: 使用环境变量传递路径或使用 `shlex.quote()` 安全转义

### 第五阶段: 集成测试和验证 (2-3天) 📋 **待实施**
- 运行完整测试套件
- 进行安全渗透测试
- 修复发现的问题
- 更新文档

---

## 如何开始实施

### 1. 查看文档
```bash
# 查看详细修复方案
cat SECURITY_FIX_PLAN.md

# 查看快速参考
cat SECURITY_QUICK_REFERENCE.md

# 查看README
cat SECURITY_README.md
```

### 2. 运行测试
```bash
# 安装测试依赖
pip install pytest pytest-cov

# 运行安全测试
pytest tests/test_security.py -v

# 查看覆盖率
pytest tests/test_security.py --cov=dlazy.security --cov-report=html
```

### 3. 运行安全检查
```bash
# 运行安全检查脚本
./security_check.sh
```

### 4. 开始修复
按照第二、三、四阶段的计划,依次修复各类安全漏洞。

---

## 安全检查清单

使用此清单跟踪修复进度:

### 代码修复
- [ ] 所有 `subprocess.run(..., shell=True)` 已替换为 `run_command_safe()`
- [ ] 所有用户输入路径已通过 `validate_path()` 验证
- [ ] 所有shell参数已通过 `sanitize_shell_arg()` 转义
- [ ] 所有文件名已通过 `sanitize_filename()` 清理
- [ ] 配置文件命令模板已通过 `validate_command_template()` 验证

### 测试验证
- [ ] 所有安全测试通过
- [ ] 测试覆盖率 >80%
- [ ] 安全检查脚本运行通过
- [ ] 进行了安全渗透测试

### 文档更新
- [ ] 更新了代码注释
- [ ] 更新了用户文档
- [ ] 记录了所有修改

---

## 风险评估

### 当前风险等级: **高**

**原因**:
- 存在命令注入漏洞,可导致系统被完全控制
- 存在路径遍历漏洞,可访问敏感文件
- 存在模板注入漏洞,可执行任意代码

### 修复后风险等级: **低**

**预期改进**:
- 所有用户输入都经过验证和转义
- 所有命令执行都是安全的
- 所有文件访问都在预期范围内
- 配置文件经过安全验证

---

## 预计时间表

| 阶段 | 任务 | 预计时间 | 状态 |
|------|------|----------|------|
| 1 | 创建安全基础设施 | 1-2天 | ✅ 已完成 |
| 2 | 修复命令注入漏洞 | 2-3天 | 📋 待实施 |
| 3 | 修复路径遍历漏洞 | 1-2天 | 📋 待实施 |
| 4 | 修复模板注入漏洞 | 2-3天 | 📋 待实施 |
| 5 | 集成测试和验证 | 2-3天 | 📋 待实施 |
| **总计** | **完整修复** | **8-13天** | **进行中** |

---

## 联系方式

如有疑问或发现问题,请联系:
- 安全问题报告: security@example.com
- 技术支持: support@example.com

---

**文档版本**: 1.0  
**最后更新**: 2026-03-13  
**状态**: 第一阶段已完成,准备进入第二阶段
