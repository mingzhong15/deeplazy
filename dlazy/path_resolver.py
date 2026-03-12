"""Path resolver for unified file path resolution between run and batch modes."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from .constants import (
    FOLDERS_FILE,
    HAMLOG_FILE,
    PROGRESS_FILE,
    OLP_TASKS_FILE,
    INFER_TASKS_FILE,
    CALC_TASKS_FILE,
    ERROR_TASKS_FILE,
    BATCH_DIR_PREFIX,
    BATCH_PADDING,
    SLURM_SUBDIR_TEMPLATE,
    OUTPUT_SUBDIR_TEMPLATE,
    TASK_DIR_PREFIX,
    TASK_PADDING,
    GROUP_PREFIX,
    GROUP_PADDING,
)

if TYPE_CHECKING:
    pass


class PathResolver(ABC):
    """Base class for path resolution."""

    @abstractmethod
    def get_workdir(self) -> Path:
        """Get working directory."""
        pass

    # ========== OLP Stage ==========

    @abstractmethod
    def get_olp_slurm_dir(self) -> Path:
        """Get OLP SLURM script directory."""
        pass

    @abstractmethod
    def get_olp_output_dir(self) -> Path:
        """Get OLP output directory."""
        pass

    def get_olp_tasks_file(self) -> Path:
        """Get OLP tasks file."""
        return self.get_olp_slurm_dir() / OLP_TASKS_FILE

    def get_olp_error_file(self) -> Path:
        """Get OLP error tasks file."""
        return self.get_olp_slurm_dir() / ERROR_TASKS_FILE

    def get_olp_progress_file(self) -> Path:
        """Get OLP progress file."""
        return self.get_olp_slurm_dir() / PROGRESS_FILE

    def get_olp_folders_file(self) -> Path:
        """Get OLP folders.dat file."""
        return self.get_olp_output_dir() / FOLDERS_FILE

    # ========== Infer Stage ==========

    @abstractmethod
    def get_infer_slurm_dir(self) -> Path:
        """Get Infer SLURM script directory."""
        pass

    @abstractmethod
    def get_infer_output_dir(self) -> Path:
        """Get Infer output directory."""
        pass

    def get_infer_tasks_file(self) -> Path:
        """Get Infer tasks file."""
        return self.get_infer_slurm_dir() / INFER_TASKS_FILE

    def get_infer_error_file(self) -> Path:
        """Get Infer error tasks file."""
        return self.get_infer_slurm_dir() / ERROR_TASKS_FILE

    def get_infer_input_source(self) -> Path:
        """Get Infer input source (from OLP output)."""
        return self.get_olp_folders_file()

    def get_infer_hamlog_file(self) -> Path:
        """Get Infer hamlog.dat file."""
        return self.get_infer_output_dir() / HAMLOG_FILE

    # ========== Calc Stage ==========

    @abstractmethod
    def get_calc_slurm_dir(self) -> Path:
        """Get Calc SLURM script directory."""
        pass

    @abstractmethod
    def get_calc_output_dir(self) -> Path:
        """Get Calc output directory."""
        pass

    def get_calc_tasks_file(self) -> Path:
        """Get Calc tasks file."""
        return self.get_calc_slurm_dir() / CALC_TASKS_FILE

    def get_calc_error_file(self) -> Path:
        """Get Calc error tasks file."""
        return self.get_calc_slurm_dir() / ERROR_TASKS_FILE

    def get_calc_progress_file(self) -> Path:
        """Get Calc progress file."""
        return self.get_calc_slurm_dir() / PROGRESS_FILE

    def get_calc_folders_file(self) -> Path:
        """Get Calc folders.dat file."""
        return self.get_calc_output_dir() / FOLDERS_FILE

    def get_calc_input_source(self) -> Path:
        """Get Calc input source (from Infer output)."""
        return self.get_infer_hamlog_file()


class RunPathResolver(PathResolver):
    """Path resolver for 'dlazy run' mode."""

    def __init__(self, workdir: Path):
        self._workdir = Path(workdir).resolve()

    def get_workdir(self) -> Path:
        return self._workdir

    def get_olp_slurm_dir(self) -> Path:
        return self._workdir / "0olp"

    def get_olp_output_dir(self) -> Path:
        return self._workdir / "0olp"

    def get_infer_slurm_dir(self) -> Path:
        return self._workdir / "1infer"

    def get_infer_output_dir(self) -> Path:
        return self._workdir / "1infer"

    def get_calc_slurm_dir(self) -> Path:
        return self._workdir / "2calc"

    def get_calc_output_dir(self) -> Path:
        return self._workdir / "2calc"


class BatchPathResolver(PathResolver):
    """Path resolver for 'dlazy batch' mode."""

    def __init__(self, workflow_root: Path, batch_index: int):
        self._workflow_root = Path(workflow_root).resolve()
        self._batch_index = batch_index
        self._batch_dir = (
            self._workflow_root / f"{BATCH_DIR_PREFIX}.{batch_index:0{BATCH_PADDING}d}"
        )

    def get_workdir(self) -> Path:
        return self._batch_dir

    def get_olp_slurm_dir(self) -> Path:
        return self._batch_dir / SLURM_SUBDIR_TEMPLATE.format("olp")

    def get_olp_output_dir(self) -> Path:
        return self._batch_dir / OUTPUT_SUBDIR_TEMPLATE.format("olp")

    def get_infer_slurm_dir(self) -> Path:
        return self._batch_dir / SLURM_SUBDIR_TEMPLATE.format("infer")

    def get_infer_output_dir(self) -> Path:
        return self._batch_dir / OUTPUT_SUBDIR_TEMPLATE.format("infer")

    def get_calc_slurm_dir(self) -> Path:
        return self._batch_dir / SLURM_SUBDIR_TEMPLATE.format("calc")

    def get_calc_output_dir(self) -> Path:
        return self._batch_dir / OUTPUT_SUBDIR_TEMPLATE.format("calc")

    # ========== Batch-specific methods ==========

    def get_todo_list_file(self) -> Path:
        """Get todo_list.json path at workflow root."""
        return self._workflow_root / "todo_list.json"

    def get_permanent_error_file(self) -> Path:
        """Get permanent error file (exceeded max retries)."""
        return self._workflow_root / "permanent_errors.jsonl"

    def get_next_batch_resolver(self) -> "BatchPathResolver":
        """Get PathResolver for the next batch."""
        return BatchPathResolver(self._workflow_root, self._batch_index + 1)

    def get_olp_task_dir(self, task_index: int) -> Path:
        """Get OLP task directory: output_olp/task.NNNNNN/"""
        task_dirname = f"{TASK_DIR_PREFIX}.{task_index:0{TASK_PADDING}d}"
        return self.get_olp_output_dir() / task_dirname

    def get_calc_task_dir(self, task_index: int) -> Path:
        """Get Calc task directory: output_calc/task.NNNNNN/"""
        task_dirname = f"{TASK_DIR_PREFIX}.{task_index:0{TASK_PADDING}d}"
        return self.get_calc_output_dir() / task_dirname

    def get_infer_group_dir(self, group_id: int) -> Path:
        """Get Infer group directory: output_infer/g.NNN/"""
        group_dirname = f"{GROUP_PREFIX}.{group_id:0{GROUP_PADDING}d}"
        return self.get_infer_output_dir() / group_dirname

    @property
    def batch_index(self) -> int:
        """Get current batch index."""
        return self._batch_index
