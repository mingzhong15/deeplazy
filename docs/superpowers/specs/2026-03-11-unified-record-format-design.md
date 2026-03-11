# 统一数据格式与路径命名规范

## 背景

当前项目中存在以下问题：

1. **路径层级过深**：result 目录使用类似 UUID 的随机路径（如 `ab/cd/efgh-ijkl-mnop-qrst-uvwxyz`），层级深且难以追溯
2. **数据格式不统一**：
   - `todo_list.json`：JSON Lines 格式
   - `folders.dat`：空格分隔格式
   - `hamlog.dat`：空格分隔格式
3. **读写接口分散**：各阶段使用不同的解析和写入逻辑

## 目标

1. 统一路径格式为 `task.XXXXX`（基于输入路径的确定性哈希）
2. 统一所有数据文件为 JSON Lines 格式
3. 提供统一的读写接口

## 设计

### 一、路径格式

#### task_id 生成规则

```python
import hashlib

def path_to_task_id(path: str) -> str:
    """基于路径生成确定性 task_id"""
    h = hashlib.md5(path.encode()).hexdigest()[:5]
    return f"task.{h}"
```

- 使用 MD5 哈希的前 5 位十六进制字符
- 相同路径始终生成相同 task_id
- 支持约 100 万任务（16^5 = 1,048,576）

#### 目录结构

| 阶段 | 结果目录 | 路径格式 |
|------|----------|----------|
| OLP | `result-olp/` | `task.XXXXX/scf/`, `task.XXXXX/geth/` |
| Infer | `result-infer/` | `g001/task.XXXXX/geth/`（按组分组） |
| Calc | `result-calc/` | `task.XXXXX/scf/`, `task.XXXXX/geth/` |

**示例**：
```
workflow-root/
├── result-olp/
│   ├── task.3a7f2/
│   │   ├── scf/
│   │   └── geth/
│   └── task.8b1c4/
│       ├── scf/
│       └── geth/
├── result-infer/
│   └── g001/
│       └── task.3a7f2/
│           └── geth/
└── result-calc/
    └── task.3a7f2/
        ├── scf/
        └── geth/
```

### 二、数据文件格式

所有数据文件统一为 **JSON Lines (.jsonl)** 格式。

#### 文件命名

| 原文件名 | 新文件名 |
|----------|----------|
| `todo_list.json` | `todo_list.jsonl` |
| `folders.dat` | `folders.jsonl` |
| `hamlog.dat` | `hamlog.jsonl` |

#### 数据结构

**todo_list.jsonl**（输入列表）：
```json
{"path": "/path/to/POSCAR"}
```

**folders.jsonl**（OLP/Calc 阶段输出）：
```json
{"path": "/path/to/POSCAR", "scf_path": "/result-olp/task.3a7f2/scf", "geth_path": "/result-olp/task.3a7f2/geth"}
```

**hamlog.jsonl**（Infer 阶段输出）：
```json
{"path": "/path/to/POSCAR", "target_path": "/result-infer/geth/task.3a7f2"}
```

### 三、统一读写接口

新增模块 `dlazy/record.py`：

```python
"""统一记录管理模块"""

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional


def path_to_task_id(path: str) -> str:
    """
    基于路径生成确定性 task_id。
    
    Args:
        path: POSCAR 文件路径
        
    Returns:
        task_id，格式为 "task.XXXXX"
    """
    h = hashlib.md5(path.encode()).hexdigest()[:5]
    return f"task.{h}"


def task_id_to_result_path(task_id: str, base_dir: Path, subdir: str = "scf") -> Path:
    """
    将 task_id 转换为结果目录路径。
    
    Args:
        task_id: 任务 ID
        base_dir: 结果根目录
        subdir: 子目录名（scf/geth）
        
    Returns:
        完整路径
    """
    return base_dir / task_id / subdir


def read_records(file_path: Path) -> List[Dict]:
    """
    读取 JSONL 文件。
    
    Args:
        file_path: 文件路径
        
    Returns:
        记录列表
    """
    if not file_path.exists():
        return []
    
    records = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                records.append(json.loads(line))
    return records


def write_record(file_path: Path, record: Dict, append: bool = True) -> None:
    """
    写入单条 JSONL 记录。
    
    Args:
        file_path: 文件路径
        record: 记录字典
        append: 是否追加模式
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(file_path, mode, encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_records(file_path: Path, records: List[Dict]) -> None:
    """
    写入多条 JSONL 记录（覆盖模式）。
    
    Args:
        file_path: 文件路径
        records: 记录列表
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

### 四、修改点清单

#### 4.1 constants.py

```python
# 文件名常量（修改）
FOLDERS_FILE = "folders.jsonl"
HAMLOG_FILE = "hamlog.jsonl"
TODO_FILE = "todo_list.jsonl"
```

#### 4.2 utils.py

- **删除**：`generate_random_paths()` 函数
- **删除**：`parse_folders_file()` 函数（用 `record.read_records()` 替代）
- **删除**：`MaterialRecord` 类（不再需要）

#### 4.3 commands.py

**OLPCommandExecutor.execute()**：
```python
# 修改前
scf_path, geth_path = generate_random_paths(ctx.result_dir)

# 修改后
task_id = path_to_task_id(poscar_path)
scf_path = ctx.result_dir / task_id / "scf"
geth_path = ctx.result_dir / task_id / "geth"
```

**写入 folders.jsonl**：
```python
# 修改前
write_text(ctx.folders_file, f"{label} {scf_path} {geth_path}\n", append=True)

# 修改后
write_record(ctx.folders_file, {
    "path": label,
    "scf_path": str(scf_path),
    "geth_path": str(geth_path)
})
```

**CalcCommandExecutor.execute()** 同理修改。

**InferCommandExecutor._append_hamlog()**：
```python
# 修改前
line = f"{record['label']} {target_path}\n"
write_text(hamlog_file, line, append=True)

# 修改后
write_record(hamlog_file, {
    "path": record["label"],
    "target_path": str(target_path)
})
```

#### 4.4 executor.py

**_read_olp_records()**：
```python
# 修改前
data = json.loads(lines[i].strip())
records.append(data["path"])

# 修改后（使用统一接口）
records = read_records(stru_log)
return [r["path"] for r in records[start:end]]
```

**_read_calc_records()**：
```python
# 修改前
parts = lines[i].strip().split()
records.append((parts[0], parts[1]))

# 修改后
records = read_records(hamlog)
return [(r["path"], r["target_path"]) for r in records[start:end]]
```

#### 4.5 workflow.py

- 更新文件名引用：`folders.dat` → `folders.jsonl`，`hamlog.dat` → `hamlog.jsonl`
- `_load_labels_from_folders()` 改用 `read_records()` 读取

### 五、向后兼容

本次修改**不保证向后兼容**。建议：

1. 新工作流直接使用新格式
2. 旧工作流完成后迁移，或提供一次性转换脚本

### 六、影响范围

| 模块 | 影响程度 |
|------|----------|
| constants.py | 低（仅修改常量） |
| utils.py | 中（删除函数） |
| record.py | 新增模块 |
| commands.py | 高（核心逻辑修改） |
| executor.py | 中（读取逻辑修改） |
| workflow.py | 低（适配新文件名） |
