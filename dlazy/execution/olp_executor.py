"""OLP stage executor."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from dlazy.core.tasks import OlpTask
from dlazy.core.validator.hdf5_integrity import HDF5IntegrityValidator
from dlazy.execution.base import Executor, ExecutorContext, TaskResult, TaskStatus

if TYPE_CHECKING:
    from dlazy.scheduler.job_manager import JobManager


class OlpExecutor(Executor):
    """Executor for OLP (Overlap) stage.

    The OLP stage runs OpenMX to compute overlap matrices.
    """

    stage = "olp"

    def __init__(
        self,
        job_manager: Optional["JobManager"] = None,
        openmx_command: str = "openmx",
        extract_command: Optional[str] = None,
        num_cores: int = 24,
        max_processes: int = 1,
        node_error_flag: Optional[Path] = None,
    ):
        """Initialize OLP executor.

        Args:
            job_manager: Optional JobManager for SLURM submission
            openmx_command: OpenMX executable command
            extract_command: Command to extract overlap matrix
            num_cores: Number of cores per task
            max_processes: Maximum parallel processes
            node_error_flag: Path to node error flag file
        """
        self.job_manager = job_manager
        self.openmx_command = openmx_command
        self.extract_command = extract_command
        self.num_cores = num_cores
        self.max_processes = max_processes
        self.node_error_flag = node_error_flag

    def prepare(self, task: OlpTask, ctx: ExecutorContext) -> Path:
        """Prepare working directory for OLP task.

        Args:
            task: OlpTask with POSCAR path
            ctx: Execution context

        Returns:
            Path to working directory
        """
        workdir = ctx.workdir / f"olp_{task.path.replace('/', '_')}"
        workdir.mkdir(parents=True, exist_ok=True)

        ctx.config["_workdir"] = str(workdir)
        ctx.config["_poscar"] = task.path

        return workdir

    def execute(self, task: OlpTask, ctx: ExecutorContext) -> TaskResult:
        """Execute OLP calculation.

        Args:
            task: OlpTask with POSCAR path
            ctx: Execution context

        Returns:
            TaskResult with output path
        """
        workdir = Path(ctx.config.get("_workdir", ctx.workdir))
        poscar = task.path

        errors = []
        warnings = []
        metrics = {}

        if self.node_error_flag and self.node_error_flag.exists():
            return TaskResult(
                status=TaskStatus.SKIPPED,
                errors=["Node error flag exists, skipping"],
                warnings=warnings,
                metrics=metrics,
            )

        try:
            # Build environment with SLURM config env_vars
            env = os.environ.copy()
            slurm_config = ctx.config.get("slurm", {})
            env.update(slurm_config.get("env_vars", {}))
            ntasks = self.num_cores // max(1, self.max_processes)
            env["OMP_NUM_THREADS"] = str(ntasks)

            create_cmd = ctx.config.get("commands", {}).get("create_infile")
            if create_cmd:
                subprocess.run(
                    create_cmd.format(poscar=poscar, scf=str(workdir)),
                    shell=True,
                    cwd=workdir,
                    check=True,
                    capture_output=True,
                    env=env,
                )

            result = subprocess.run(
                self.openmx_command,
                shell=True,
                cwd=workdir,
                capture_output=True,
                text=True,
                env=env,
            )

            if result.returncode != 0:
                if "NODE ERROR" in result.stdout or "NODE ERROR" in result.stderr:
                    if self.node_error_flag:
                        self.node_error_flag.touch()
                    return TaskResult(
                        status=TaskStatus.FAILED,
                        errors=["Node error detected"],
                        warnings=warnings,
                        metrics=metrics,
                    )
                errors.append(f"OpenMX failed: {result.stderr}")

            if self.extract_command:
                extract_result = subprocess.run(
                    self.extract_command,
                    shell=True,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                if extract_result.returncode != 0:
                    warnings.append(f"Extract warning: {extract_result.stderr}")

            overlap_file = workdir / "overlaps.h5"
            if not overlap_file.exists():
                overlap_file = workdir / "overlap.h5"

            if errors:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    output_path=overlap_file if overlap_file.exists() else None,
                    errors=errors,
                    warnings=warnings,
                    metrics=metrics,
                )

            return TaskResult(
                status=TaskStatus.SUCCESS,
                output_path=overlap_file,
                warnings=warnings,
                metrics=metrics,
            )

        except subprocess.TimeoutExpired:
            return TaskResult(
                status=TaskStatus.FAILED,
                errors=["OpenMX execution timed out"],
                warnings=warnings,
                metrics=metrics,
            )
        except Exception as e:
            return TaskResult(
                status=TaskStatus.FAILED,
                errors=[f"Unexpected error: {e}"],
                warnings=warnings,
                metrics=metrics,
            )

    def validate(self, result: TaskResult, ctx: ExecutorContext) -> bool:
        """Validate OLP output.

        Args:
            result: TaskResult to validate
            ctx: Execution context

        Returns:
            True if validation passed
        """
        if not result.output_path or not result.output_path.exists():
            result.add_error("Output file not found")
            return False

        validator = HDF5IntegrityValidator()
        validation = validator.validate(result.output_path)

        if not validation.is_valid:
            for error in validation.errors:
                result.add_error(error)
            return False

        result.validation_results.append(validation)
        return True

    def cleanup(self, task: OlpTask, ctx: ExecutorContext) -> None:
        """Clean up OLP working directory.

        Args:
            task: Task that was executed
            ctx: Execution context
        """
        workdir = ctx.config.get("_workdir")
        if workdir:
            cleanup_path = Path(workdir)
            if cleanup_path.exists() and cleanup_path.is_dir():
                try:
                    shutil.rmtree(cleanup_path)
                except Exception:
                    pass
