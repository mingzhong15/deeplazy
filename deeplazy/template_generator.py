"""SLURM 提交脚本生成器（生成内嵌Python代码的脚本）"""

from pathlib import Path
from typing import Any, Dict, List


def _format_modules(modules: List[str]) -> str:
    """格式化模块加载命令"""
    if not modules:
        return ""
    lines = ["module purge"]
    for mod in modules:
        lines.append(f"module load {mod}")
    return "\n".join(lines)


def _format_env_vars(env_vars: Dict[str, Any]) -> str:
    """格式化环境变量设置"""
    if not env_vars:
        return ""
    lines = []
    for key, value in env_vars.items():
        lines.append(f"export {key}={value}")
    return "\n".join(lines)


def _format_sys_path(software_config: Dict[str, Any]) -> str:
    """生成 sys.path.append 代码"""
    deeplazy_path = software_config.get("deeplazy_path", "")
    if not deeplazy_path:
        return ""
    return f"sys.path.append('{deeplazy_path}')"


def generate_embedded_olp_script(
    python_path: str,
    config_path: str,
    batch_size: int,
    slurm_config: Dict[str, Any],
    software_config: Dict[str, Any],
) -> str:
    """
    生成内嵌Python代码的OLP SLURM脚本

    Args:
        python_path: Python解释器路径
        config_path: 全局配置文件路径
        batch_size: 批处理大小
        slurm_config: SLURM配置
        software_config: 软件配置

    Returns:
        SLURM脚本内容
    """
    job_name = slurm_config.get("job_name", "B-olp")
    partition = slurm_config.get("partition", "th3k")
    nodes = slurm_config.get("nodes", 1)
    ntasks = slurm_config.get("ntasks_per_node", 64)
    time_limit = slurm_config.get("time", "2-00:00:00")
    array_size = slurm_config.get("array_size", 10)
    modules = slurm_config.get("modules", [])
    env_vars = slurm_config.get("env_vars", {})

    modules_section = _format_modules(modules)
    env_vars_section = _format_env_vars(env_vars)
    sys_path_line = _format_sys_path(software_config)

    return f"""#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name={job_name}
#SBATCH --array=1-{array_size}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={ntasks}
#SBATCH --time={time_limit}

{modules_section}
{env_vars_section}

export BATCH_SIZE={batch_size}
export START=$(( ($SLURM_ARRAY_TASK_ID - 1) * $BATCH_SIZE ))
export END=$(( $SLURM_ARRAY_TASK_ID * $BATCH_SIZE ))

echo "[OLP] Starting at: $(date)"
echo "[OLP] Running on: $(hostname)"
echo "[OLP] Job ID: $SLURM_JOB_ID"
echo "[OLP] Array ID: $SLURM_ARRAY_TASK_ID"
echo "[OLP] Processing: $START to $END"

{python_path} - <<'PYTHON_EOF'
import os
import sys

{sys_path_line}

from deeplazy.executor import WorkflowExecutor

try:
    result = WorkflowExecutor.run_olp_stage(
        global_config='{config_path}',
        start=int(os.environ['START']),
        end=int(os.environ['END'])
    )
    print(f"[OLP] 完成: {{result}}")
except Exception as e:
    print(f"[OLP] 错误: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF

echo "[OLP] Finished at: $(date)"
"""


def generate_embedded_infer_script(
    python_path: str,
    config_path: str,
    slurm_config: Dict[str, Any],
    software_config: Dict[str, Any],
) -> str:
    """
    生成内嵌Python代码的Infer SLURM脚本

    Args:
        python_path: Python解释器路径
        config_path: 全局配置文件路径
        slurm_config: SLURM配置
        software_config: 软件配置

    Returns:
        SLURM脚本内容
    """
    job_name = slurm_config.get("job_name", "B-infer")
    partition = slurm_config.get("partition", "th3k")
    nodes = slurm_config.get("nodes", 1)
    ntasks = slurm_config.get("ntasks_per_node", 1)
    cpus_per_task = slurm_config.get("cpus_per_task", 64)
    time_limit = slurm_config.get("time", "2-00:00:00")
    array_size = slurm_config.get("array_size", 20)
    modules = slurm_config.get("modules", [])
    env_vars = slurm_config.get("env_vars", {})

    modules_section = _format_modules(modules)
    env_vars_section = _format_env_vars(env_vars)
    sys_path_line = _format_sys_path(software_config)

    return f"""#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name={job_name}
#SBATCH --array=1-{array_size}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={ntasks}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --time={time_limit}

{modules_section}
{env_vars_section}

export GROUP_INDEX=$SLURM_ARRAY_TASK_ID

echo "[Infer] Starting at: $(date)"
echo "[Infer] Running on: $(hostname)"
echo "[Infer] Job ID: $SLURM_JOB_ID"
echo "[Infer] Array ID: $SLURM_ARRAY_TASK_ID"
echo "[Infer] Group Index: $GROUP_INDEX"

{python_path} - <<'PYTHON_EOF'
import os
import sys

{sys_path_line}

from deeplazy.executor import WorkflowExecutor

try:
    result = WorkflowExecutor.run_infer_stage(
        global_config='{config_path}',
        group_index=int(os.environ['GROUP_INDEX'])
    )
    print(f"[Infer] 完成: {{result}}")
except Exception as e:
    print(f"[Infer] 错误: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF

echo "[Infer] Finished at: $(date)"
"""


def generate_embedded_calc_script(
    python_path: str,
    config_path: str,
    batch_size: int,
    slurm_config: Dict[str, Any],
    software_config: Dict[str, Any],
) -> str:
    """
    生成内嵌Python代码的Calc SLURM脚本

    Args:
        python_path: Python解释器路径
        config_path: 全局配置文件路径
        batch_size: 批处理大小
        slurm_config: SLURM配置
        software_config: 软件配置

    Returns:
        SLURM脚本内容
    """
    job_name = slurm_config.get("job_name", "B-calc")
    partition = slurm_config.get("partition", "th3k")
    nodes = slurm_config.get("nodes", 1)
    ntasks = slurm_config.get("ntasks_per_node", 64)
    time_limit = slurm_config.get("time", "4-00:00:00")
    array_size = slurm_config.get("array_size", 50)
    modules = slurm_config.get("modules", [])
    env_vars = slurm_config.get("env_vars", {})

    modules_section = _format_modules(modules)
    env_vars_section = _format_env_vars(env_vars)
    sys_path_line = _format_sys_path(software_config)

    return f"""#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name={job_name}
#SBATCH --array=1-{array_size}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks-per-node={ntasks}
#SBATCH --time={time_limit}

{modules_section}
{env_vars_section}

export BATCH_SIZE={batch_size}
export START=$(( ($SLURM_ARRAY_TASK_ID - 1) * $BATCH_SIZE ))
export END=$(( $SLURM_ARRAY_TASK_ID * $BATCH_SIZE ))

echo "[Calc] Starting at: $(date)"
echo "[Calc] Running on: $(hostname)"
echo "[Calc] Job ID: $SLURM_JOB_ID"
echo "[Calc] Array ID: $SLURM_ARRAY_TASK_ID"
echo "[Calc] Processing: $START to $END"

{python_path} - <<'PYTHON_EOF'
import os
import sys

{sys_path_line}

from deeplazy.executor import WorkflowExecutor

try:
    result = WorkflowExecutor.run_calc_stage(
        global_config='{config_path}',
        start=int(os.environ['START']),
        end=int(os.environ['END'])
    )
    print(f"[Calc] 完成: {{result}}")
except Exception as e:
    print(f"[Calc] 错误: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF

echo "[Calc] Finished at: $(date)"
"""


def generate_submit_script(
    stage_name: str,
    stage_dir: Path,
    stage_config: Dict[str, Any],
    python_path: str,
    config_path: str,
    software_config: Dict[str, Any],
) -> Path:
    """
    生成 SLURM 提交脚本（内嵌Python代码）

    Args:
        stage_name: 阶段名称 (0olp, 1infer, 2calc)
        stage_dir: 阶段目录路径
        stage_config: 该阶段的配置字典
        python_path: Python 解释器路径
        config_path: 全局配置文件路径
        software_config: 软件配置

    Returns:
        生成的脚本文件路径
    """
    slurm_config = stage_config.get("slurm", {})

    if stage_name == "0olp":
        batch_size = slurm_config.get("batch_size", 200)
        content = generate_embedded_olp_script(
            python_path, config_path, batch_size, slurm_config, software_config
        )
    elif stage_name == "1infer":
        content = generate_embedded_infer_script(
            python_path, config_path, slurm_config, software_config
        )
    elif stage_name == "2calc":
        batch_size = slurm_config.get("batch_size", 40)
        content = generate_embedded_calc_script(
            python_path, config_path, batch_size, slurm_config, software_config
        )
    else:
        raise ValueError(f"未知阶段: {stage_name}")

    script_path = stage_dir / "submit.sh"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)

    return script_path
