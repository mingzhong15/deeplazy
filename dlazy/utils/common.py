"""工具函数（从 common/utils.py 迁移并增强）"""

from __future__ import annotations

import json
import logging
import random
import re
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Sequence, Tuple

import yaml

try:
    import h5py
except ImportError:
    h5py = None

from ..constants import (
    FOLDERS_FILE,
    HAMLOG_FILE,
    ERROR_FILE,
    PROGRESS_FILE,
    GROUP_INFO_FILE,
    GROUP_MAPPING_FILE,
    GROUP_PREFIX,
    GROUP_PADDING,
    INPUTS_SUBDIR,
    OUTPUTS_SUBDIR,
    CONFIG_SUBDIR,
    GETH_SUBDIR,
    DFT_SUBDIR,
    GETH_NEW_SUBDIR,
    RESULT_OLP_DIR,
    RESULT_INFER_DIR,
    PATH_0OLP_FOLDERS,
    PATH_1INFER_HAMLOG,
    PATH_RESULT_GETH,
    OVERLAP_FILENAME,
    HAMILTONIAN_FILENAME,
    HAMILTONIAN_PRED_FILENAME,
    HAMILTONIAN_LINK_FILENAME,
    AUX_FILENAMES,
    INFER_TEMPLATE,
    BATCH_DIR_PREFIX,
    BATCH_PADDING,
    TASK_DIR_PREFIX,
    TASK_PADDING,
)


LOGGER_NAME = "restart_workflow.3steps"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取全局日志记录器"""
    logger = logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s][%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


@dataclass(frozen=True)
class MaterialRecord:
    """代表单条材料记录"""

    label: str
    scf_path: str
    geth_path: str

    @property
    def short_path(self) -> Path:
        path = Path(self.geth_path)
        if len(path.parts) < 3:
            raise ValueError(f"路径长度不足，无法提取末尾三级路径: {path}")
        return Path(*path.parts[-3:])

    def resolve_under(self, base: Path) -> Path:
        return base / self.short_path


def parse_folders_file(file_path: Path) -> List[MaterialRecord]:
    """解析 folders.dat 文件"""
    records: List[MaterialRecord] = []
    logger = get_logger("utils")
    logger.info("读取材料记录: %s", file_path)

    with open(file_path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) < 3:
                logger.warning("第 %s 行字段不足: %s", line_no, stripped)
                continue
            label, scf_path, geth_path = parts[:3]
            records.append(
                MaterialRecord(label=label, scf_path=scf_path, geth_path=geth_path)
            )

    logger.info("共解析到 %s 条材料记录", len(records))
    return records


def validate_h5(file_path: Path) -> Tuple[bool, str]:
    """验证 HDF5 文件完整性"""
    if not file_path.exists():
        return False, f"文件不存在: {file_path}"

    if h5py is None:
        return True, "h5py未安装，跳过验证"

    try:
        with h5py.File(file_path, "r") as f:

            def visitor(name, obj):
                if isinstance(obj, h5py.Dataset):
                    shape = obj.shape
                    if shape:
                        _ = obj[0] if len(shape) > 0 else obj[()]

            f.visititems(visitor)
    except Exception as exc:
        return False, f"读取失败: {exc}"
    return True, "ok"


def bulk_validate_h5(files: Iterable[Path]) -> List[Tuple[Path, str]]:
    """批量验证 HDF5 文件"""
    failures: List[Tuple[Path, str]] = []
    for file_path in files:
        ok, message = validate_h5(file_path)
        if not ok:
            failures.append((file_path, message))
    return failures


def run_subprocess(
    command: Sequence[str] | str,
    *,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    check: bool = True,
    shell: bool | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """执行 shell 命令"""
    logger = get_logger("subprocess")
    if isinstance(command, str):
        shell = True if shell is None else shell
        display_cmd = command
    else:
        shell = False if shell is None else shell
        display_cmd = " ".join(command)

    logger.info("执行命令: %s", display_cmd)
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        shell=shell,
        check=check,
        text=True,
        capture_output=capture_output,
    )

    if result.stdout:
        logger.debug("stdout: %s", result.stdout.strip())
    if result.stderr:
        logger.debug("stderr: %s", result.stderr.strip())

    return result


def ensure_directory(path: Path) -> None:
    """确保目录存在"""
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str, append: bool = False) -> None:
    """写入文本文件"""
    ensure_directory(path.parent)
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as handle:
        handle.write(content)


def chunk_records(
    records: Sequence[MaterialRecord], num_groups: int, seed: Optional[int]
) -> List[List[MaterialRecord]]:
    """将记录随机分组"""
    if num_groups <= 0:
        raise ValueError("num_groups 必须为正整数")

    rng = random.Random(seed)
    shuffled = list(records)
    rng.shuffle(shuffled)

    groups: List[List[MaterialRecord]] = [[] for _ in range(num_groups)]
    for index, record in enumerate(shuffled):
        groups[index % num_groups].append(record)
    return groups


def iter_expected_files(
    records: Iterable[MaterialRecord], base_dir: Path, filename: str
) -> Iterable[Path]:
    """迭代预期文件路径"""
    for record in records:
        yield record.resolve_under(base_dir) / filename


def load_json_config(path: Path) -> Dict[str, Any]:
    """加载 JSON 配置"""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


_config_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def load_yaml_config(path: Path, use_cache: bool = True) -> Dict[str, Any]:
    """加载 YAML 配置，支持基于 mtime 的缓存"""
    path_str = str(path.resolve())

    if use_cache and path_str in _config_cache:
        cached_mtime, cached_config = _config_cache[path_str]
        current_mtime = path.stat().st_mtime
        if current_mtime == cached_mtime:
            return cached_config

    with open(path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if use_cache:
        _config_cache[path_str] = (path.stat().st_mtime, config)

    return config


def resolve_path(base_dir: Path, raw_path: str | Path) -> Path:
    """解析路径"""
    path = Path(raw_path)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def resolve_section_paths(
    section: MutableMapping[str, Any], base_dir: Path, keys: Iterable[str]
) -> None:
    """解析配置段中的路径"""
    for key in keys:
        if key in section and section[key] is not None:
            section[key] = str(resolve_path(base_dir, section[key]))


def _expand_software_vars(text: str, software: Dict[str, Any]) -> str:
    """展开 {var} 和 {var.subvar} 形式的变量引用"""
    if not isinstance(text, str):
        return text

    pattern = r"\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}"

    def replace(match):
        key_path = match.group(1)
        keys = key_path.split(".")
        value = software
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return match.group(0)
        return str(value)

    return re.sub(pattern, replace, text)


def _expand_section_vars(obj: Any, software: Dict[str, Any]) -> Any:
    """递归展开配置中的变量"""
    if isinstance(obj, dict):
        return {k: _expand_section_vars(v, software) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_section_vars(item, software) for item in obj]
    elif isinstance(obj, str):
        return _expand_software_vars(obj, software)
    return obj


def load_global_config_section(
    global_config_path: Path, section: str, config_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    从全局配置中提取指定section的配置，并展开software变量。

    Args:
        global_config_path: 全局配置文件路径
        section: 配置段名称 (olp, infer, calc)
        config_dir: 原配置文件所在目录（已弃用，保留向后兼容）

    Returns:
        该section的配置字典（已展开software变量）
    """
    if not global_config_path.exists():
        raise FileNotFoundError(f"全局配置文件不存在: {global_config_path}")

    global_config = load_yaml_config(global_config_path)

    if section not in global_config:
        raise KeyError(f"全局配置中未找到 section: {section}")

    software = global_config.get("software", {})
    return _expand_section_vars(global_config[section], software)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """深度合并两个字典"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_workflow_root(stage_dir: Path) -> Path:
    """获取工作流根目录"""
    return stage_dir.parent


def get_result_olp_dir(workflow_root: Path) -> Path:
    """获取 overlap 计算结果目录"""
    return workflow_root / RESULT_OLP_DIR


def get_result_infer_dir(workflow_root: Path) -> Path:
    """获取推理结果目录"""
    return workflow_root / RESULT_INFER_DIR


def get_0olp_folders_path(stage_dir: Path) -> Path:
    """获取 0olp 阶段的 folders.dat 路径"""
    return stage_dir.parent / "0olp" / FOLDERS_FILE


def get_1infer_hamlog_path(stage_dir: Path) -> Path:
    """获取 1infer 阶段的 hamlog.dat 路径"""
    return stage_dir.parent / "1infer" / HAMLOG_FILE


def get_result_geth_dir(workflow_root: Path) -> Path:
    """获取推理输出的 geth 目录"""
    return workflow_root / RESULT_INFER_DIR / GETH_SUBDIR


def generate_random_paths(base_dir: Path) -> Tuple[Path, Path]:
    """生成随机 SCF 和 GETH 路径"""

    def gen_path():
        h = secrets.token_hex(16)
        return f"{h[:2]}/{h[2:4]}/{h[4:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

    scf_path = base_dir / gen_path()
    geth_path = base_dir / gen_path()

    return scf_path, geth_path


def get_batch_dir(workflow_root: Path, batch_index: int) -> Path:
    """Get batch directory path."""
    return workflow_root / f"{BATCH_DIR_PREFIX}.{batch_index:0{BATCH_PADDING}d}"


def get_task_dir(batch_dir: Path, task_index: int) -> Path:
    """Get task directory path within a batch."""
    return batch_dir / f"{TASK_DIR_PREFIX}.{task_index:0{TASK_PADDING}d}"


def get_existing_batch_count(workflow_root: Path) -> int:
    """Count existing batch directories and return the next available batch index.

    Args:
        workflow_root: Workflow root directory containing batch.* directories

    Returns:
        Next available batch index (0 if no existing batches)
    """
    batch_dirs = list(workflow_root.glob(f"{BATCH_DIR_PREFIX}.*"))
    if not batch_dirs:
        return 0

    max_index = -1
    for bd in batch_dirs:
        try:
            index = int(bd.name.split(".")[-1])
            max_index = max(max_index, index)
        except ValueError:
            continue

    return max_index + 1


def get_next_backup_index(workflow_root: Path, prefix: str = "todo_list.origin") -> int:
    """Get next backup index for todo_list backups.

    Args:
        workflow_root: Workflow root directory
        prefix: Backup file prefix (default: "todo_list.origin")

    Returns:
        Next available index (1 if no existing backups)

    Example:
        If todo_list.origin.001 and todo_list.origin.002 exist, returns 3
    """
    idx = 1
    while (workflow_root / f"{prefix}.{idx:03d}").exists():
        idx += 1
    return idx
