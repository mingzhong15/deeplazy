# Deeplazy 项目统一修复计划

**日期**: 2026-03-13  
**版本**: 1.0  
**状态**: 待实施

---

## 执行摘要

基于多代理并行分析，发现项目存在 **5 大类 20+ 个问题**，涵盖安全、并发、资源管理、错误处理和性能优化。本计划整合所有修复方案，分阶段实施。

### 问题优先级分布

| 严重程度 | 数量 | 类别 |
|---------|------|------|
| 🔴 严重 (P0) | 6 | 安全漏洞、并发竞态、资源泄漏 |
| 🟠 中等 (P1) | 8 | 性能瓶颈、错误处理不一致 |
| 🟡 轻微 (P2) | 6 | 代码质量、边界情况 |

### 预期收益

- **安全性**: 修复 3 个严重漏洞，防止命令注入/路径遍历/模板注入
- **稳定性**: 解决竞态条件，提高并发可靠性
- **性能**: 整体提升 30-50%
- **可维护性**: 统一错误处理，降低代码复杂度

---

## 一、修复计划总览

### 阶段划分

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          实施时间线 (3-4周)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  第1周: 安全修复 (P0)                                                   │
│  ├── Day 1-2: 安全基础设施 - security.py, config_validator.py          │
│  ├── Day 3-4: 命令注入修复 - commands.py                                │
│  └── Day 5: 路径验证 + 模板安全 - cli.py, template_generator.py        │
│                                                                         │
│  第2周: 并发安全 + 资源管理 (P0-P1)                                     │
│  ├── Day 1-2: 文件锁机制 - file_lock.py, pid_lock.py                  │
│  ├── Day 3-4: 资源管理器 - resource_manager.py                         │
│  └── Day 5: 修改 batch_workflow.py, workflow.py                        │
│                                                                         │
│  第3周: 错误处理统一 (P1)                                               │
│  ├── Day 1-2: 新异常体系 - exceptions.py                                │
│  ├── Day 3-4: 统一错误处理中心 - unified_error_handler.py              │
│  └── Day 5: 迁移脚本 + 测试验证                                         │
│                                                                         │
│  第4周: 性能优化 + 验证 (P1-P2)                                         │
│  ├── Day 1-2: 配置缓存 + SLURM 缓存                                     │
│  ├── Day 3: 增量文件操作优化                                            │
│  ├── Day 4: 性能监控埋点                                                │
│  └── Day 5: 综合测试 + 文档更新                                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、详细修复方案

### 2.1 安全问题修复 (第1周) - 🔴 P0

#### 问题清单

| # | 问题 | 位置 | 严重程度 |
|---|------|------|---------|
| 1 | 命令注入漏洞 | commands.py:133, 260, 841 | 🔴 严重 |
| 2 | 路径遍历漏洞 | cli.py:18, 154 | 🔴 严重 |
| 3 | 模板注入漏洞 | template_generator.py:130 | 🔴 高 |

#### 新增文件

| 文件 | 用途 |
|------|------|
| `dlazy/security.py` | 安全工具函数（路径验证、命令转义） |
| `dlazy/config_validator.py` | 配置文件安全验证 |
| `tests/test_security.py` | 安全测试用例 |

#### 核心修复代码

```python
# dlazy/security.py - 核心函数

def validate_path(path, base_dir=None, allow_symlinks=True, must_exist=False) -> Path:
    """验证路径安全性，防止路径遍历攻击"""

def sanitize_shell_arg(arg) -> str:
    """安全转义 shell 参数，防止命令注入"""

def run_command_safe(command_template, args=None, **kwargs) -> subprocess.CompletedProcess:
    """安全执行 shell 命令"""

def validate_command_template(template) -> bool:
    """验证命令模板是否安全"""
```

#### 修改点

**commands.py 修复示例:**

```python
# 修复前
command_create = ctx.config["commands"]["create_infile"].format(poscar=path, scf=scf_path)
subprocess.run(command_create, shell=True, check=True)

# 修复后
from .security import validate_path, run_command_safe

validated_path = validate_path(path, must_exist=True)
run_command_safe(
    ctx.config["commands"]["create_infile"],
    args={'poscar': validated_path, 'scf': scf_path},
    check=True,
)
```

#### 测试要求

- 24 个安全测试用例
- 覆盖路径验证、Shell 注入、模板注入、配置验证
- 渗透测试验证

---

### 2.2 并发安全问题修复 (第2周前半) - 🔴 P0

#### 问题清单

| # | 问题 | 位置 | 严重程度 |
|---|------|------|---------|
| 1 | 状态文件并发访问无保护 | batch_workflow.py:134 | 🔴 严重 |
| 2 | PID 检测 TOCTOU 竞态 | batch_workflow.py:599 | 🔴 严重 |
| 3 | JSONL 追加无锁 | record_utils.py:99 | 🔴 严重 |

#### 新增文件

| 文件 | 用途 |
|------|------|
| `dlazy/file_lock.py` | 文件锁工具类（独占锁/共享锁） |
| `dlazy/pid_lock.py` | PID 锁增强（陈旧锁清理） |

#### 核心修复代码

```python
# dlazy/file_lock.py

class FileLock:
    """独占文件锁，支持超时"""
    def acquire(self) -> bool: ...
    def release(self) -> None: ...

class SharedFileLock:
    """共享文件锁，支持多读者"""
    def acquire_shared(self) -> bool: ...

def atomic_write_json(filepath: Path, data: Dict) -> None:
    """原子写入 JSON 文件"""

def atomic_append_jsonl(filepath: Path, records: list) -> None:
    """原子追加 JSONL 记录"""

# dlazy/pid_lock.py

class PIDLock:
    """进程锁，自动清理陈旧锁"""
    def acquire(self) -> bool: ...
    def is_locked(self) -> bool: ...
```

#### 修改点

**batch_workflow.py 修复:**

```python
# 修复前
with open(self.ctx.state_file, "w") as f:
    json.dump(state, f)

# 修复后
from .file_lock import atomic_write_json

atomic_write_json(self.ctx.state_file, state)
```

**PID 检测修复:**

```python
# 修复前
def _is_running(self) -> bool:
    if not pid_file.exists():
        return False
    os.kill(pid, 0)  # TOCTOU 竞态

# 修复后
from .pid_lock import PIDLock

def __init__(self, ...):
    self._pid_lock = PIDLock(pid_file)

def _is_running(self) -> bool:
    return self._pid_lock.is_locked()
```

---

### 2.3 资源管理问题修复 (第2周后半) - 🔴 P0 / 🟠 P1

#### 问题清单

| # | 问题 | 位置 | 严重程度 |
|---|------|------|---------|
| 1 | 文件句柄泄漏 | commands.py:187 | 🔴 严重 |
| 2 | 监控线程阻塞 | commands.py:197 | 🟠 中等 |
| 3 | 工作目录全局变更 | commands.py:140 | 🟠 中等 |

#### 新增文件

| 文件 | 用途 |
|------|------|
| `dlazy/resource_manager.py` | 统一资源管理器 |

#### 核心修复代码

```python
# dlazy/resource_manager.py

@contextmanager
def safe_file(path: Path, mode: str, encoding: str = "utf-8"):
    """安全文件句柄上下文管理器"""

@contextmanager
def safe_chdir(target_dir: Path):
    """安全工作目录切换"""

def run_monitored_process(command, stdout_path, error_patterns, **kwargs) -> tuple[bool, int]:
    """运行带监控的进程 - 使用轮询避免阻塞"""
```

#### 修改点

**commands.py 修复:**

```python
# 修复前
proc = subprocess.Popen(
    command,
    stdout=open("openmx.std", "w"),  # 泄漏
    shell=True,
)

# 修复后
from .resource_manager import run_monitored_process, safe_chdir

with safe_chdir(scf_path):
    error_detected, returncode = run_monitored_process(
        command,
        stdout_path=Path("openmx.std"),
        error_patterns=["Requested nodes are busy"],
    )
```

---

### 2.4 错误处理统一 (第3周) - 🟠 P1

#### 问题清单

| # | 问题 | 严重程度 |
|---|------|---------|
| 1 | Calc 阶段异常吞没 | 🔴 严重 |
| 2 | 双重错误记录不同步 | 🟠 中等 |
| 3 | 重试计数分散 | 🟡 轻微 |
| 4 | 异常继承关系混乱 | 🟠 中等 |
| 5 | 错误上下文丢失 | 🟠 中等 |

#### 新增文件

| 文件 | 用途 |
|------|------|
| `dlazy/unified_error_handler.py` | 统一错误处理中心 |
| `dlazy/retry_config.py` | 统一重试策略 |
| `scripts/migrate_errors.py` | 迁移脚本 |

#### 重构文件

| 文件 | 操作 |
|------|------|
| `dlazy/exceptions.py` | 重构异常体系 |
| `dlazy/error_handler.py` | 添加兼容层 |
| `dlazy/monitor.py` | 废弃，合并到新系统 |

#### 核心设计

**新异常体系:**

```python
class WorkflowError(Exception):
    """工作流基础异常"""
    failure_type: FailureType = FailureType.UNKNOWN_ERROR
    
    def __init__(self, message, *, stage=None, task_path=None, 
                 original_exception=None, context=None):
        # 保留原始堆栈
        self.traceback_str = traceback.format_exc() if original_exception else None

class AbortException(WorkflowError):
    """快速失败异常 - 现在继承自 WorkflowError"""
    pass
```

**统一错误处理中心:**

```python
class ErrorHandler:
    """统一错误处理中心"""
    
    def record_error(self, error, *, stage, task_path, batch_id, task_id) -> ErrorRecord:
        """记录错误 - 同时更新文件和内存"""
    
    def should_abort(self, failure_type, max_retries) -> bool:
        """判断是否中断工作流"""
```

**统一重试策略:**

```python
class RetryManager:
    """三层重试统一管理"""
    
    def should_retry_task(self, path, stage, failure_type) -> bool: ...
    def should_retry_stage(self, stage) -> bool: ...
    def should_retry_cross_batch(self) -> bool: ...
```

---

### 2.5 性能优化 (第4周) - 🟠 P1 / 🟡 P2

#### 问题清单

| # | 问题 | 预期提升 |
|---|------|---------|
| 1 | 配置重复加载 | 15-20% |
| 2 | SLURM 状态检查瓶颈 | 10-15% |
| 3 | Infer 阶段冗余操作 | 5-10% |
| 4 | 符号链接无去重 | 2-5% |

#### 新增文件

| 文件 | 用途 |
|------|------|
| `dlazy/performance.py` | 性能监控模块 |
| `dlazy/slurm_cache.py` | SLURM 状态缓存 |
| `dlazy/optimized_commands.py` | 优化的文件操作 |

#### 核心优化

**配置缓存:**

```python
_config_cache: Dict[str, Tuple[float, Dict]] = {}

def load_yaml_config(path: Path, use_cache: bool = True) -> Dict:
    """基于 mtime 的配置缓存"""
    if use_cache and path_str in _config_cache:
        cached_mtime, cached_config = _config_cache[path_str]
        if path.stat().st_mtime == cached_mtime:
            return cached_config
    # 重新加载...
```

**SLURM 缓存:**

```python
class SlurmStateCache:
    """SLURM 状态缓存"""
    
    def __init__(self, default_ttl=60.0, terminal_ttl=300.0):
        # 运行中: 60秒缓存
        # 终止状态: 300秒缓存
```

**增量文件操作:**

```python
def _smart_ensure_symlink(source: Path, target: Path) -> bool:
    """智能创建符号链接，避免重复操作"""
    if not _should_relink(source, target):
        return False  # 已是正确链接
    # 创建新链接...
```

---

## 三、实施检查清单

### 第1周: 安全修复

- [ ] 实现 `dlazy/security.py`
- [ ] 实现 `dlazy/config_validator.py`
- [ ] 修复 `commands.py` 所有 `shell=True` 调用
- [ ] 修复 `cli.py` 路径验证
- [ ] 修复 `template_generator.py` 模板安全
- [ ] 编写 24 个安全测试
- [ ] 通过渗透测试

### 第2周: 并发 + 资源

- [ ] 实现 `dlazy/file_lock.py`
- [ ] 实现 `dlazy/pid_lock.py`
- [ ] 实现 `dlazy/resource_manager.py`
- [ ] 修改 `batch_workflow.py` 使用原子写入
- [ ] 修改 `workflow.py` 使用 PID 锁
- [ ] 修改 `commands.py` 使用资源管理器
- [ ] 修改 `record_utils.py` 使用原子追加

### 第3周: 错误处理

- [ ] 重构 `dlazy/exceptions.py`
- [ ] 实现 `dlazy/unified_error_handler.py`
- [ ] 实现 `dlazy/retry_config.py`
- [ ] 修复 `commands.py` 异常吞没
- [ ] 更新 `workflow.py` 使用新系统
- [ ] 编写迁移脚本
- [ ] 验证新旧系统兼容

### 第4周: 性能 + 验证

- [ ] 实现 `dlazy/performance.py`
- [ ] 实现 `dlazy/slurm_cache.py`
- [ ] 实现配置缓存
- [ ] 实现增量文件操作
- [ ] 关键路径性能埋点
- [ ] 综合测试
- [ ] 文档更新

---

## 四、测试策略

### 4.1 单元测试

| 模块 | 测试文件 | 用例数 |
|------|---------|-------|
| 安全 | `tests/test_security.py` | 24 |
| 文件锁 | `tests/test_file_lock.py` | 10 |
| 资源管理 | `tests/test_resource_manager.py` | 8 |
| 错误处理 | `tests/test_error_handler.py` | 15 |
| 性能 | `tests/test_performance.py` | 10 |

### 4.2 集成测试

- 端到端工作流测试
- 并发场景测试
- 错误恢复测试
- 性能回归测试

### 4.3 压力测试

- 大批量任务测试 (>10000)
- 高并发写入测试
- 长时间运行稳定性测试

---

## 五、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 安全修复破坏现有功能 | 中 | 高 | 完整回归测试 |
| 迁移脚本数据丢失 | 低 | 高 | 备份原始文件 |
| 性能优化引入 bug | 中 | 中 | 性能回归测试 |
| 并发修复引入新竞态 | 低 | 高 | 并发压力测试 |

---

## 六、验收标准

### 功能验收

- [ ] 所有安全测试通过
- [ ] 无命令注入/路径遍历漏洞
- [ ] 状态文件并发写入正确
- [ ] 异常正确传递，无吞没
- [ ] 错误记录统一且一致
- [ ] 历史数据迁移成功

### 性能验收

- [ ] 配置加载性能提升 >10x
- [ ] SLURM 查询缓存命中率 >90%
- [ ] 重试场景文件操作减少 >50%
- [ ] 整体性能提升 30-50%

### 质量验收

- [ ] 测试覆盖率 >80%
- [ ] 无新增 lint 警告
- [ ] 文档完整更新
- [ ] 代码审查通过

---

## 七、相关文档

| 文档 | 路径 |
|------|------|
| 安全修复详细方案 | `SECURITY_FIX_PLAN.md` |
| 性能优化详细方案 | `docs/performance_optimization_plan.md` |
| 错误处理设计方案 | `docs/superpowers/specs/2026-03-13-unified-error-handling-design.md` |
| 快速参考指南 | `SECURITY_QUICK_REFERENCE.md` |

---

## 八、新增文件汇总

| 文件 | 周次 | 用途 |
|------|------|------|
| `dlazy/security.py` | 第1周 | 安全工具函数 |
| `dlazy/config_validator.py` | 第1周 | 配置安全验证 |
| `tests/test_security.py` | 第1周 | 安全测试 |
| `dlazy/file_lock.py` | 第2周 | 文件锁机制 |
| `dlazy/pid_lock.py` | 第2周 | PID 锁增强 |
| `dlazy/resource_manager.py` | 第2周 | 资源管理器 |
| `tests/test_file_lock.py` | 第2周 | 文件锁测试 |
| `tests/test_resource_manager.py` | 第2周 | 资源管理测试 |
| `dlazy/unified_error_handler.py` | 第3周 | 统一错误处理 |
| `dlazy/retry_config.py` | 第3周 | 统一重试策略 |
| `scripts/migrate_errors.py` | 第3周 | 错误迁移脚本 |
| `tests/test_error_handler.py` | 第3周 | 错误处理测试 |
| `dlazy/performance.py` | 第4周 | 性能监控 |
| `dlazy/slurm_cache.py` | 第4周 | SLURM 缓存 |
| `dlazy/optimized_commands.py` | 第4周 | 优化文件操作 |
| `tests/test_performance.py` | 第4周 | 性能测试 |

---

**文档版本**: 1.0  
**最后更新**: 2026-03-13  
**负责人**: 开发团队
