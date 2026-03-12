"""SLURM submit script generator with dynamic batch_size calculation."""

import math
from pathlib import Path
from typing import Any, Dict, List, Optional


def _format_modules(modules: List[str]) -> str:
    """Format module load commands."""
    if not modules:
        return ""
    lines = ["module purge"]
    for mod in modules:
        lines.append(f"module load {mod}")
    return "\n".join(lines)


def _format_env_vars(env_vars: Dict[str, Any]) -> str:
    """Format environment variable settings."""
    if not env_vars:
        return ""
    lines = []
    for key, value in env_vars.items():
        lines.append(f"export {key}={value}")
    return "\n".join(lines)


def _format_sys_path(software_config: Dict[str, Any]) -> str:
    """Generate sys.path.append code."""
    dlazy_path = software_config.get("dlazy_path", "")
    if not dlazy_path:
        return ""
    return f"sys.path.append('{dlazy_path}')"


def calculate_batch_size(num_tasks: int, array_size: int) -> int:
    """Calculate tasks per job based on total tasks and desired array size."""
    if array_size <= 0:
        array_size = 1
    if num_tasks <= 0:
        return 1
    return math.ceil(num_tasks / array_size)


def generate_embedded_olp_script(
    python_path: str,
    config_path: str,
    num_tasks: int,
    slurm_config: Dict[str, Any],
    software_config: Dict[str, Any],
) -> str:
    """
    Generate OLP SLURM script with dynamic batch_size.

    Args:
        python_path: Python interpreter path
        config_path: Global config file path
        num_tasks: Number of tasks in this batch
        slurm_config: SLURM configuration
        software_config: Software configuration

    Returns:
        SLURM script content
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

    batch_size = calculate_batch_size(num_tasks, array_size)
    actual_array_size = min(array_size, num_tasks)
    if actual_array_size < 1:
        actual_array_size = 1

    return f"""#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name={job_name}
#SBATCH --array=1-{actual_array_size}
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
echo "[OLP] Processing: $START to $END (batch_size={batch_size})"

{python_path} - <<'PYTHON_EOF'
import os
import sys

{sys_path_line}

from dlazy.executor import WorkflowExecutor

try:
    result = WorkflowExecutor.run_olp_stage(
        global_config='{config_path}',
        start=int(os.environ['START']),
        end=int(os.environ['END'])
    )
    print(f"[OLP] Complete: {{result}}")
except Exception as e:
    print(f"[OLP] Error: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF

echo "[OLP] Finished at: $(date)"
"""


def generate_embedded_infer_script(
    python_path: str,
    config_path: str,
    num_groups: int,
    slurm_config: Dict[str, Any],
    software_config: Dict[str, Any],
) -> str:
    """
    Generate Infer SLURM script with dynamic array size.

    Args:
        python_path: Python interpreter path
        config_path: Global config file path
        num_groups: Number of groups to process
        slurm_config: SLURM configuration
        software_config: Software configuration

    Returns:
        SLURM script content
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

    actual_array_size = min(array_size, num_groups)
    if actual_array_size < 1:
        actual_array_size = 1

    return f"""#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name={job_name}
#SBATCH --array=1-{actual_array_size}
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

from dlazy.executor import WorkflowExecutor

try:
    result = WorkflowExecutor.run_infer_stage(
        global_config='{config_path}',
        group_index=int(os.environ['GROUP_INDEX'])
    )
    print(f"[Infer] Complete: {{result}}")
except Exception as e:
    print(f"[Infer] Error: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF

echo "[Infer] Finished at: $(date)"
"""


def generate_embedded_calc_script(
    python_path: str,
    config_path: str,
    num_tasks: int,
    slurm_config: Dict[str, Any],
    software_config: Dict[str, Any],
) -> str:
    """
    Generate Calc SLURM script with dynamic batch_size.

    Args:
        python_path: Python interpreter path
        config_path: Global config file path
        num_tasks: Number of tasks in this batch
        slurm_config: SLURM configuration
        software_config: Software configuration

    Returns:
        SLURM script content
    """
    job_name = slurm_config.get("job_name", "B-calc")
    partition = slurm_config.get("partition", "th3k")
    nodes = slurm_config.get("nodes", 1)
    ntasks = slurm_config.get("ntasks_per_node", 64)
    time_limit = slurm_config.get("time", "4-00:00:00")
    array_size = slurm_config.get("array_size", 10)
    modules = slurm_config.get("modules", [])
    env_vars = slurm_config.get("env_vars", {})

    modules_section = _format_modules(modules)
    env_vars_section = _format_env_vars(env_vars)
    sys_path_line = _format_sys_path(software_config)

    batch_size = calculate_batch_size(num_tasks, array_size)
    actual_array_size = min(array_size, num_tasks)
    if actual_array_size < 1:
        actual_array_size = 1

    return f"""#!/bin/bash
#SBATCH --no-requeue
#SBATCH --job-name={job_name}
#SBATCH --array=1-{actual_array_size}
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
echo "[Calc] Processing: $START to $END (batch_size={batch_size})"

{python_path} - <<'PYTHON_EOF'
import os
import sys

{sys_path_line}

from dlazy.executor import WorkflowExecutor

try:
    result = WorkflowExecutor.run_calc_stage(
        global_config='{config_path}',
        start=int(os.environ['START']),
        end=int(os.environ['END'])
    )
    print(f"[Calc] Complete: {{result}}")
except Exception as e:
    print(f"[Calc] Error: {{e}}", file=sys.stderr)
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
    num_tasks: Optional[int] = None,
) -> Path:
    """
    Generate SLURM submit script with dynamic batch_size.

    Args:
        stage_name: Stage name (0olp, 1infer, 2calc)
        stage_dir: Stage directory path
        stage_config: Stage configuration dict
        python_path: Python interpreter path
        config_path: Global config file path
        software_config: Software configuration
        num_tasks: Number of tasks (for dynamic batch_size calculation)

    Returns:
        Path to generated script
    """
    slurm_config = stage_config.get("slurm", {})

    if stage_name == "0olp":
        content = generate_embedded_olp_script(
            python_path=python_path,
            config_path=config_path,
            num_tasks=num_tasks or 1,
            slurm_config=slurm_config,
            software_config=software_config,
        )
    elif stage_name == "1infer":
        num_groups = stage_config.get("num_groups", num_tasks or 10)
        content = generate_embedded_infer_script(
            python_path=python_path,
            config_path=config_path,
            num_groups=num_groups,
            slurm_config=slurm_config,
            software_config=software_config,
        )
    elif stage_name == "2calc":
        content = generate_embedded_calc_script(
            python_path=python_path,
            config_path=config_path,
            num_tasks=num_tasks or 1,
            slurm_config=slurm_config,
            software_config=software_config,
        )
    else:
        raise ValueError(f"Unknown stage: {stage_name}")

    stage_dir.mkdir(parents=True, exist_ok=True)
    script_path = stage_dir / "submit.sh"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)

    return script_path
