"""Infer stage executor."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from dlazy.core.tasks import InferTask
from dlazy.core.validator.hdf5_integrity import HDF5IntegrityValidator
from dlazy.execution.base import Executor, ExecutorContext, TaskResult, TaskStatus
from dlazy.constants import (
    OVERLAP_FILENAME,
    HAMILTONIAN_FILENAME,
    HAMILTONIAN_PRED_FILENAME,
    HAMILTONIAN_LINK_FILENAME,
    INPUTS_SUBDIR,
    OUTPUTS_SUBDIR,
    CONFIG_SUBDIR,
    GETH_SUBDIR,
    DFT_SUBDIR,
    GETH_NEW_SUBDIR,
    AUX_FILENAMES,
    TASK_DIR_PREFIX,
    TASK_PADDING,
)
from dlazy.utils.concurrency import ensure_directory

if TYPE_CHECKING:
    from dlazy.scheduler.job_manager import JobManager


def _ensure_symlink(source: Path, target: Path) -> None:
    """Create symlink, removing existing target if needed."""
    if not source.exists():
        raise FileNotFoundError(f"Source path not found: {source}")

    ensure_directory(target.parent)
    if target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()

    os.symlink(source, target)


class InferExecutor(Executor):
    """Executor for Infer stage.

    The Infer stage runs DeepH model inference to predict Hamiltonians
    from overlap matrices.
    """

    stage = "infer"

    def __init__(
        self,
        job_manager: Optional["JobManager"] = None,
        transform_command: Optional[str] = None,
        infer_command: Optional[str] = None,
        transform_reverse_command: Optional[str] = None,
        num_groups: int = 1,
        model_dir: Optional[Path] = None,
        dataset_prefix: str = "infer",
        parallel: int = 1,
    ):
        """Initialize Infer executor.

        Args:
            job_manager: Optional JobManager for SLURM submission
            transform_command: Command to transform data format
            infer_command: DeepH inference command
            transform_reverse_command: Command to reverse transform
            num_groups: Number of groups for batch processing
            model_dir: Directory containing DeepH model
            dataset_prefix: Prefix for dataset naming
            parallel: Parallelism level for transform commands
        """
        self.job_manager = job_manager
        self.transform_command = transform_command
        self.infer_command = infer_command
        self.transform_reverse_command = transform_reverse_command
        self.num_groups = num_groups
        self.model_dir = Path(model_dir) if model_dir else None
        self.dataset_prefix = dataset_prefix
        self.parallel = parallel

    def prepare(self, task: InferTask, ctx: ExecutorContext) -> Path:
        """Prepare working directory for Infer task.

        Creates directory structure and symlinks overlap files from scf_path.

        Args:
            task: InferTask with path and scf_path
            ctx: Execution context

        Returns:
            Path to prepared working directory
        """
        workdir = ctx.workdir / f"infer_{hash(task.path) % 100000:05d}"
        workdir.mkdir(parents=True, exist_ok=True)

        # Store config for later use
        ctx.config["_workdir"] = str(workdir)
        ctx.config["_poscar"] = task.path
        ctx.config["_scf_path"] = task.scf_path

        # Create standard directory structure
        inputs_geth_dir = workdir / INPUTS_SUBDIR / GETH_SUBDIR
        inputs_dft_dir = workdir / INPUTS_SUBDIR / DFT_SUBDIR
        outputs_dir = workdir / OUTPUTS_SUBDIR
        config_dir = workdir / CONFIG_SUBDIR
        final_geth_dir = workdir / GETH_SUBDIR

        ensure_directory(inputs_geth_dir)
        ensure_directory(inputs_dft_dir)
        ensure_directory(outputs_dir)
        ensure_directory(config_dir)
        ensure_directory(final_geth_dir)

        # Symlink overlap files from scf_path (OLP output)
        scf_path = Path(task.scf_path)
        if not scf_path.exists():
            raise FileNotFoundError(f"SCF/OLP path not found: {scf_path}")

        overlap_file = scf_path / OVERLAP_FILENAME
        if not overlap_file.exists():
            raise FileNotFoundError(f"Overlap file not found: {overlap_file}")

        # Link the entire OLP directory to inputs/geth/task.000000
        task_dirname = f"{TASK_DIR_PREFIX}.{0:0{TASK_PADDING}d}"
        target_task_dir = inputs_geth_dir / task_dirname
        _ensure_symlink(scf_path, target_task_dir)

        return workdir

    def execute(self, task: InferTask, ctx: ExecutorContext) -> TaskResult:
        """Execute Infer calculation.

        Runs transform, inference, and transform_reverse commands.

        Args:
            task: InferTask with path and scf_path
            ctx: Execution context

        Returns:
            TaskResult with output path to hamiltonians.h5
        """
        workdir = Path(ctx.config.get("_workdir", ctx.workdir))

        errors: List[str] = []
        warnings: List[str] = []
        metrics: Dict[str, Any] = {}

        inputs_dir = workdir / INPUTS_SUBDIR
        outputs_dir = workdir / OUTPUTS_SUBDIR
        final_geth_dir = workdir / GETH_SUBDIR

        env = os.environ.copy()
        slurm_config = ctx.config.get("slurm", {})
        env.update(slurm_config.get("env_vars", {}))

        try:
            # Step 1: Run transform (geth -> dft format)
            if self.transform_command:
                inputs_geth_dir = inputs_dir / GETH_SUBDIR
                inputs_dft_dir = inputs_dir / DFT_SUBDIR

                cmd = self.transform_command.format(
                    input_dir=inputs_geth_dir,
                    output_dir=inputs_dft_dir,
                    parallel=self.parallel,
                )
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                if result.returncode != 0:
                    errors.append(f"Transform failed: {result.stderr}")

            if errors:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    errors=errors,
                    warnings=warnings,
                    metrics=metrics,
                )

            # Step 2: Generate inference config and run inference
            if self.infer_command:
                config_path = self._generate_infer_config(workdir, ctx)
                cmd = self.infer_command.format(config_path=config_path)
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                if result.returncode != 0:
                    errors.append(f"Inference failed: {result.stderr}")

            if errors:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    errors=errors,
                    warnings=warnings,
                    metrics=metrics,
                )

            # Step 3: Find latest output directory
            latest_output = self._find_latest_output(outputs_dir, warnings)

            if latest_output is None:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    errors=["No inference output directory found"],
                    warnings=warnings,
                    metrics=metrics,
                )

            # Step 4: Link inference outputs and run transform_reverse
            output_dft_dir = latest_output / DFT_SUBDIR
            geth_new_dir = workdir / GETH_NEW_SUBDIR
            ensure_directory(geth_new_dir)

            # Link predicted Hamiltonians
            task_dirname = f"{TASK_DIR_PREFIX}.{0:0{TASK_PADDING}d}"
            source_ham = output_dft_dir / task_dirname / HAMILTONIAN_PRED_FILENAME

            if not source_ham.exists():
                errors.append(f"Predicted Hamiltonian not found: {source_ham}")
                return TaskResult(
                    status=TaskStatus.FAILED,
                    errors=errors,
                    warnings=warnings,
                    metrics=metrics,
                )

            target_task_dir = geth_new_dir / task_dirname
            ensure_directory(target_task_dir)
            target_ham = target_task_dir / HAMILTONIAN_LINK_FILENAME

            if target_ham.exists() or target_ham.is_symlink():
                target_ham.unlink()
            os.symlink(source_ham, target_ham)

            # Link auxiliary files from inputs/dft
            inputs_dft_dir = inputs_dir / DFT_SUBDIR
            for filename in AUX_FILENAMES:
                source_file = inputs_dft_dir / task_dirname / filename
                if source_file.exists():
                    target_file = target_task_dir / filename
                    if target_file.exists() or target_file.is_symlink():
                        target_file.unlink()
                    os.symlink(source_file, target_file)
                else:
                    warnings.append(f"Auxiliary file not found: {source_file}")

            # Step 5: Run transform_reverse
            if self.transform_reverse_command:
                cmd = self.transform_reverse_command.format(
                    input_dir=geth_new_dir,
                    output_dir=final_geth_dir,
                    parallel=self.parallel,
                )
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                if result.returncode != 0:
                    errors.append(f"Transform_reverse failed: {result.stderr}")

            if errors:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    errors=errors,
                    warnings=warnings,
                    metrics=metrics,
                )

            # Output path
            output_path = final_geth_dir / task_dirname / HAMILTONIAN_FILENAME

            return TaskResult(
                status=TaskStatus.SUCCESS,
                output_path=output_path,
                warnings=warnings,
                metrics=metrics,
            )

        except subprocess.TimeoutExpired:
            return TaskResult(
                status=TaskStatus.FAILED,
                errors=["Inference execution timed out"],
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
        """Validate Infer output.

        Checks that hamiltonians.h5 exists and passes HDF5 integrity validation.

        Args:
            result: TaskResult to validate
            ctx: Execution context

        Returns:
            True if validation passed
        """
        if not result.output_path or not result.output_path.exists():
            result.add_error("Hamiltonians output file not found")
            return False

        validator = HDF5IntegrityValidator()
        validation = validator.validate(result.output_path)

        if not validation.is_valid:
            for error in validation.errors:
                result.add_error(error)
            return False

        result.validation_results.append(validation)
        return True

    def cleanup(self, task: InferTask, ctx: ExecutorContext) -> None:
        """Clean up Infer working directory.

        Removes temporary files but keeps final output.

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

    def _generate_infer_config(self, workdir: Path, ctx: ExecutorContext) -> Path:
        """Generate inference configuration file.

        Args:
            workdir: Working directory
            ctx: Execution context

        Returns:
            Path to generated config file
        """
        # Use template from constants or inline
        config_template = ctx.config.get("infer_template")
        if config_template:
            template_path = Path(config_template)
            if template_path.exists():
                content = template_path.read_text(encoding="utf-8")
            else:
                content = self._get_default_template()
        else:
            content = self._get_default_template()

        inputs_dir = workdir / INPUTS_SUBDIR
        outputs_dir = workdir / OUTPUTS_SUBDIR
        group_id = "g001"

        config_content = content.format(
            inputs_dir=str(inputs_dir),
            outputs_dir=str(outputs_dir),
            dataset_name=f"{self.dataset_prefix}_{group_id}",
            model_dir=str(self.model_dir) if self.model_dir else "",
        )

        config_path = workdir / CONFIG_SUBDIR / "infer.toml"
        ensure_directory(config_path.parent)
        config_path.write_text(config_content, encoding="utf-8")

        return config_path

    def _get_default_template(self) -> str:
        """Get default inference config template."""
        return """[data]
inputs_dir = "{inputs_dir}"
outputs_dir = "{outputs_dir}"
dataset_name = "{dataset_name}"

[model]
model_dir = "{model_dir}"
"""

    def _find_latest_output(
        self, outputs_dir: Path, warnings: List[str]
    ) -> Optional[Path]:
        """Find the latest inference output directory.

        Args:
            outputs_dir: Root outputs directory
            warnings: List to append warning messages

        Returns:
            Path to latest output directory or None
        """
        if not outputs_dir.exists():
            warnings.append(f"Outputs directory not found: {outputs_dir}")
            return None

        subdirs = [item for item in outputs_dir.iterdir() if item.is_dir()]
        if not subdirs:
            warnings.append(f"No output subdirectories in: {outputs_dir}")
            return None

        return max(subdirs, key=lambda item: item.stat().st_mtime)
