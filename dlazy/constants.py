"""工作流常量定义（从 common/constants.py 迁移）"""

# ============================================
# 文件名常量
# ============================================
OVERLAP_FILENAME = "overlaps.h5"
HAMILTONIAN_FILENAME = "hamiltonians.h5"
HAMILTONIAN_PRED_FILENAME = "hamiltonian_pred.h5"
HAMILTONIAN_LINK_FILENAME = "hamiltonian.h5"

# ============================================
# 中间文件常量
# ============================================
FOLDERS_FILE = "folders.dat"
HAMLOG_FILE = "hamlog.dat"
ERROR_FILE = "error.dat"
PROGRESS_FILE = "progress"
GROUP_INFO_FILE = "group_info.json"
GROUP_MAPPING_FILE = "group_mapping.txt"

# ============================================
# 目录结构常量 (相对于工作流根目录)
# ============================================
RESULT_OLP_DIR = "result-olp"
RESULT_INFER_DIR = "result-infer"

# infer 子目录
INPUTS_SUBDIR = "inputs"
OUTPUTS_SUBDIR = "outputs"
CONFIG_SUBDIR = "config"
GETH_SUBDIR = "geth"
DFT_SUBDIR = "dft"
GETH_NEW_SUBDIR = "geth.new"

# ============================================
# 辅助文件
# ============================================
AUX_FILENAMES = ["POSCAR", "info.json"]
INFER_TEMPLATE = "templates/infer.toml.j2"

# ============================================
# 分组配置
# ============================================
GROUP_PREFIX = "g"
GROUP_PADDING = 3

# ============================================
# 阶段间数据传递路径 (相对于各阶段目录)
# ============================================
# 0olp -> 1infer
PATH_0OLP_FOLDERS = "../0olp/folders.dat"

# 1infer -> 2calc
PATH_1INFER_HAMLOG = "../1infer/hamlog.dat"
PATH_RESULT_GETH = "../result-infer/geth"

# ============================================
# Unified Record Files (JSON Lines)
# ============================================
OLP_TASKS_FILE = "olp_tasks.jsonl"
INFER_TASKS_FILE = "infer_tasks.jsonl"
CALC_TASKS_FILE = "calc_tasks.jsonl"
ERROR_TASKS_FILE = "error_tasks.jsonl"

# ============================================
# Batch State
# ============================================
BATCH_STATE_FILE = "batch_state.json"
BATCH_DIR_PREFIX = "batch"
BATCH_PADDING = 5
TASK_DIR_PREFIX = "task"
TASK_PADDING = 6

# ============================================
# Stage Subdirectories (within task dir)
# ============================================
OLP_SUBDIR = "olp"
INFER_SUBDIR = "infer"
SCF_SUBDIR = "scf"

# ============================================
# Monitor Configuration
# ============================================
from dlazy.exceptions import FailureType

DEFAULT_MAX_RETRIES = {
    FailureType.SUBMIT_FAILED: 0,
    FailureType.SLURM_FAILED: 3,
    FailureType.NODE_ERROR: 3,
    FailureType.CALC_ERROR: -1,
}

MONITOR_STATE_FILE = "monitor_state.json"
