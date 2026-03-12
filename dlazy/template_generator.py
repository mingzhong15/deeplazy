"""SLURM submit script generator with dynamic batch_size calculation."""

import json
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


def _parse_batch_index_from_workdir(workdir: str) -> Optional[int]:
    """Parse batch_index from workdir (batch.NNNNN format)."""
    if not workdir:
        return None
    import re

    match = re.search(r"batch\.(\d+)", workdir)
    if match:
        return int(match.group(1))
    return None


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
    """
    Generate OLP SLURM script with dynamic batch_size.

    Args:
        python_path: Python interpreter path
        config_path: Global config file path
        num_tasks: Number of tasks in this batch
        slurm_config: SLURM configuration
        software_config: Software configuration
        tasks_file: Path to olp_tasks.jsonl (for batch mode)
        workdir: Working directory (batch.00000/ for batch mode)
        batch_index: Batch index (optional, will be parsed from workdir if not provided)
        workflow_root: Workflow root directory (for batch mode)

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

    use_batch_mode = batch_index is not None or workflow_root is not None

    if use_batch_mode:
        workflow_root_arg = workflow_root or workdir
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
import json

{sys_path_line}

from pathlib import Path
from dlazy.path_resolver import BatchPathResolver
from dlazy.commands import OLPCommandExecutor
from dlazy.record_utils import read_olp_tasks, append_infer_task, InferTask
from dlazy.utils import load_global_config_section

def parse_batch_index(workdir):
    import re
    match = re.search(r'batch\.(\d+)', str(workdir))
    return int(match.group(1)) if match else None

try:
    workflow_root = Path('{workflow_root_arg}')
    batch_index = {batch_index} if ({batch_index} is not None) else parse_batch_index('{workdir}')

    if batch_index is None:
        raise ValueError("batch_index is required for batch mode")

    resolver = BatchPathResolver(workflow_root, batch_index)
    config = load_global_config_section(Path('{config_path}'), '0olp')

    start = int(os.environ['START'])
    end = int(os.environ['END'])

    tasks_file = resolver.get_olp_tasks_file()
    all_tasks = read_olp_tasks(tasks_file)
    tasks = all_tasks[start:end]

    print(f"[OLP] Processing {{len(tasks)}} tasks ({{start}}:{{end}})")

    success = 0
    failed = 0
    for task_index, task in enumerate(tasks, start=start):
        try:
            result = OLPCommandExecutor.execute_batch(task_index, task, resolver, config)
            append_infer_task(resolver.get_infer_tasks_file(), result)
            success += 1
        except Exception as e:
            print(f"[OLP] Task {{task_index}} failed: {{e}}")
            failed += 1

    print(f"[OLP] Complete: success={{success}}, failed={{failed}}")
except Exception as e:
    print(f"[OLP] Error: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF

echo "[OLP] Finished at: $(date)"
"""

    stru_log_arg = f", stru_log='{tasks_file}'" if tasks_file else ""
    workdir_arg = f", workdir='{workdir}'" if workdir else ""

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
        end=int(os.environ['END']){stru_log_arg}{workdir_arg}
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
    workdir: Optional[str] = None,
    batch_index: Optional[int] = None,
    workflow_root: Optional[str] = None,
) -> str:
    """
    Generate Infer SLURM script with dynamic array size.

    Args:
        python_path: Python interpreter path
        config_path: Global config file path
        num_groups: Number of groups to process
        slurm_config: SLURM configuration
        software_config: Software configuration
        workdir: Working directory (batch.00000/ for batch mode)
        batch_index: Batch index (optional, will be parsed from workdir if not provided)
        workflow_root: Workflow root directory (for batch mode)

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

    use_batch_mode = batch_index is not None or workflow_root is not None

    if use_batch_mode:
        workflow_root_arg = workflow_root or workdir
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
import json
import random

{sys_path_line}

from pathlib import Path
from dlazy.path_resolver import BatchPathResolver
from dlazy.commands import InferCommandExecutor
from dlazy.record_utils import read_infer_tasks, append_calc_task
from dlazy.utils import load_global_config_section

def parse_batch_index(workdir):
    import re
    match = re.search(r'batch\.(\d+)', str(workdir))
    return int(match.group(1)) if match else None

def chunk_tasks(tasks, num_groups, random_seed=137):
    random.seed(random_seed)
    shuffled = tasks.copy()
    random.shuffle(shuffled)
    chunk_size = len(shuffled) // num_groups
    if chunk_size == 0:
        chunk_size = 1
    chunks = []
    for i in range(0, len(shuffled), chunk_size):
        chunks.append(shuffled[i:i+chunk_size])
    return chunks

try:
    workflow_root = Path('{workflow_root_arg}')
    batch_index = {batch_index} if ({batch_index} is not None) else parse_batch_index('{workdir}')

    if batch_index is None:
        raise ValueError("batch_index is required for batch mode")

    resolver = BatchPathResolver(workflow_root, batch_index)
    config = load_global_config_section(Path('{config_path}'), '1infer')

    group_index = int(os.environ['GROUP_INDEX'])
    num_groups = config.get('num_groups', {num_groups})
    random_seed = config.get('random_seed', 137)
    model_dir = Path(config.get('model_dir', '/path/to/model'))
    dataset_prefix = config.get('dataset_prefix', 'dataset')
    parallel = config.get('parallel', 56)

    infer_tasks_file = resolver.get_infer_tasks_file()
    all_tasks = read_infer_tasks(infer_tasks_file)

    groups = chunk_tasks(all_tasks, num_groups, random_seed)
    if group_index - 1 >= len(groups):
        print(f"[Infer] Group index {{group_index}} out of range ({{len(groups)}} groups)")
        sys.exit(0)

    group_tasks = groups[group_index - 1]
    print(f"[Infer] Processing group {{group_index}} with {{len(group_tasks)}} tasks")

    calc_tasks = InferCommandExecutor.execute_batch(
        group_index,
        group_tasks,
        resolver,
        config,
        model_dir,
        dataset_prefix,
        parallel,
    )

    for calc_task in calc_tasks:
        append_calc_task(resolver.get_calc_tasks_file(), calc_task)

    print(f"[Infer] Complete: {{len(calc_tasks)}} calc tasks generated")
except Exception as e:
    print(f"[Infer] Error: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF

echo "[Infer] Finished at: $(date)"
"""

    workdir_arg = f", workdir='{workdir}'" if workdir else ""

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
        group_index=int(os.environ['GROUP_INDEX']){workdir_arg}
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
    tasks_file: Optional[str] = None,
    workdir: Optional[str] = None,
    batch_index: Optional[int] = None,
    workflow_root: Optional[str] = None,
) -> str:
    """
    Generate Calc SLURM script with dynamic batch_size.

    Args:
        python_path: Python interpreter path
        config_path: Global config file path
        num_tasks: Number of tasks in this batch
        slurm_config: SLURM configuration
        software_config: Software configuration
        tasks_file: Path to calc_tasks.jsonl (for batch mode)
        workdir: Working directory (batch.00000/ for batch mode)
        batch_index: Batch index (optional, will be parsed from workdir if not provided)
        workflow_root: Workflow root directory (for batch mode)

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

    use_batch_mode = batch_index is not None or workflow_root is not None

    if use_batch_mode:
        workflow_root_arg = workflow_root or workdir
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
import json

{sys_path_line}

from pathlib import Path
from dlazy.path_resolver import BatchPathResolver
from dlazy.commands import CalcCommandExecutor
from dlazy.record_utils import read_calc_tasks
from dlazy.utils import load_global_config_section

def parse_batch_index(workdir):
    import re
    match = re.search(r'batch\.(\d+)', str(workdir))
    return int(match.group(1)) if match else None

try:
    workflow_root = Path('{workflow_root_arg}')
    batch_index = {batch_index} if ({batch_index} is not None) else parse_batch_index('{workdir}')

    if batch_index is None:
        raise ValueError("batch_index is required for batch mode")

    resolver = BatchPathResolver(workflow_root, batch_index)
    config = load_global_config_section(Path('{config_path}'), '2calc')

    start = int(os.environ['START'])
    end = int(os.environ['END'])

    tasks_file = resolver.get_calc_tasks_file()
    all_tasks = read_calc_tasks(tasks_file)
    tasks = all_tasks[start:end]

    print(f"[Calc] Processing {{len(tasks)}} tasks ({{start}}:{{end}})")

    success = 0
    failed = 0
    for task_index, task in enumerate(tasks, start=start):
        try:
            status, label = CalcCommandExecutor.execute_batch(task_index, task, resolver, config)
            if status == 'success':
                success += 1
            else:
                failed += 1
                print(f"[Calc] Task {{task_index}} failed: {{label}}")
        except Exception as e:
            failed += 1
            print(f"[Calc] Task {{task_index}} exception: {{e}}")

    print(f"[Calc] Complete: success={{success}}, failed={{failed}}")
except Exception as e:
    print(f"[Calc] Error: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc()
    sys.exit(1)
PYTHON_EOF

echo "[Calc] Finished at: $(date)"
"""

    stru_log_arg = f", stru_log='{tasks_file}'" if tasks_file else ""
    workdir_arg = f", workdir='{workdir}'" if workdir else ""

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
        end=int(os.environ['END']){stru_log_arg}{workdir_arg}
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
    tasks_file: Optional[str] = None,
    workdir: Optional[str] = None,
    batch_index: Optional[int] = None,
    workflow_root: Optional[str] = None,
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
        tasks_file: Path to tasks file (olp_tasks.jsonl or calc_tasks.jsonl)
        workdir: Working directory (batch.00000/ for batch mode)
        batch_index: Batch index (optional, will be parsed from workdir if not provided)
        workflow_root: Workflow root directory (for batch mode)

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
            tasks_file=tasks_file,
            workdir=workdir,
            batch_index=batch_index,
            workflow_root=workflow_root,
        )
    elif stage_name == "1infer":
        num_groups = stage_config.get("num_groups", num_tasks or 10)
        content = generate_embedded_infer_script(
            python_path=python_path,
            config_path=config_path,
            num_groups=num_groups,
            slurm_config=slurm_config,
            software_config=software_config,
            workdir=workdir,
            batch_index=batch_index,
            workflow_root=workflow_root,
        )
    elif stage_name == "2calc":
        content = generate_embedded_calc_script(
            python_path=python_path,
            config_path=config_path,
            num_tasks=num_tasks or 1,
            slurm_config=slurm_config,
            software_config=software_config,
            tasks_file=tasks_file,
            workdir=workdir,
            batch_index=batch_index,
            workflow_root=workflow_root,
        )
    else:
        raise ValueError(f"Unknown stage: {stage_name}")

    stage_dir.mkdir(parents=True, exist_ok=True)
    script_path = stage_dir / "submit.sh"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(content)

    return script_path
