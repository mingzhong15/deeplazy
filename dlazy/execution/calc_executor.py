"""Calc stage executor for DFT recalculation."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from dlazy.constants import (
    HAMILTONIAN_FILENAME,
    SCF_SUBDIR,
    GETH_SUBDIR,
)
from dlazy.core.tasks import CalcTask
from dlazy.core.validator.hdf5_integrity import HDF5IntegrityValidator
from dlazy.core.validator.scf_convergence import SCFConvergenceValidator
from dlazy.execution.base import Executor, ExecutorContext, TaskResult, TaskStatus
from dlazy.utils.security import run_command_safe, safe_format_command
from dlazy.utils.concurrency import ensure_directory

if TYPE_CHECKING:
    from dlazy.scheduler.job_manager import JobManager


class CalcExecutor(Executor):
    """Executor for Calc (DFT recalculation) stage.

    The Calc stage runs OpenMX SCF calculations using predicted Hamiltonians
    from the Infer stage as initial guesses.
    """

    stage = "calc"

    def __init__(
        self,
        job_manager: Optional["JobManager"] = None,
        openmx_command: str = "openmx",
        num_cores: int = 24,
        max_processes: int = 1,
        node_error_flag: Optional[Path] = None,
    ):
        """Initialize Calc executor.

        Args:
            job_manager: Optional JobManager for SLURM submission
            openmx_command: OpenMX SCF calculation command
            num_cores: Number of cores per task
            max_processes: Maximum parallel processes
            node_error_flag: Path to node error flag file
        """
        self.job_manager = job_manager
        self.openmx_command = openmx_command
        self.num_cores = num_cores
        self.max_processes = max_processes
        self.node_error_flag = node_error_flag

    def prepare(self, task: CalcTask, ctx: ExecutorContext) -> Path:
        """Prepare working directory for Calc task.

        Creates the working directory structure and symlinks the predicted
        Hamiltonian from the Infer stage.

        Args:
            task: CalcTask with geth_path from Infer output
            ctx: Execution context

        Returns:
            Path to prepared working directory
        """
        # Create task working directory
        task_name = Path(task.path).name if "/" in task.path else task.path
        workdir = ctx.workdir / f"calc_{task_name.replace('/', '_')}"
        ensure_directory(workdir)

        # Create subdirectories
        scf_dir = workdir / SCF_SUBDIR
        geth_dir = workdir / GETH_SUBDIR
        ensure_directory(scf_dir)
        ensure_directory(geth_dir)

        # Store paths in context for execute()
        ctx.config["_workdir"] = str(workdir)
        ctx.config["_scf_dir"] = str(scf_dir)
        ctx.config["_geth_dir"] = str(geth_dir)

        # Symlink predicted Hamiltonian from Infer output
        infer_geth_dir = Path(task.geth_path)
        pred_ham = infer_geth_dir / HAMILTONIAN_FILENAME

        if pred_ham.exists():
            target_ham = scf_dir / HAMILTONIAN_FILENAME
            if target_ham.exists() or target_ham.is_symlink():
                target_ham.unlink()
            os.symlink(pred_ham, target_ham)
        else:
            # Will be caught during execute()
            ctx.config["_pred_ham_missing"] = True

        return workdir

    def execute(self, task: CalcTask, ctx: ExecutorContext) -> TaskResult:
        """Execute Calc SCF calculation.

        Runs OpenMX SCF calculation using the predicted Hamiltonian as
        initial guess. Monitors for node errors and SCF convergence failures.

        Args:
            task: CalcTask to execute
            ctx: Execution context

        Returns:
            TaskResult with status and output information
        """
        workdir = Path(ctx.config.get("_workdir", ctx.workdir))
        scf_dir = Path(ctx.config.get("_scf_dir", workdir / SCF_SUBDIR))
        geth_dir = Path(ctx.config.get("_geth_dir", workdir / GETH_SUBDIR))

        errors: List[str] = []
        warnings: List[str] = []
        metrics: Dict[str, Any] = {}

        # Check for node error flag
        if self.node_error_flag and self.node_error_flag.exists():
            return TaskResult(
                status=TaskStatus.SKIPPED,
                errors=["Node error flag exists, skipping"],
                warnings=warnings,
                metrics=metrics,
            )

        # Check if predicted Hamiltonian was missing
        if ctx.config.get("_pred_ham_missing"):
            return TaskResult(
                status=TaskStatus.FAILED,
                errors=[f"Predicted Hamiltonian not found: {task.geth_path}"],
                warnings=warnings,
                metrics=metrics,
            )

        try:
            # 1. Create input files
            create_cmd = ctx.config.get("commands", {}).get("create_infile")
            if create_cmd:
                run_command_safe(
                    create_cmd,
                    args={"poscar": task.path, "scf": str(scf_dir)},
                    cwd=scf_dir,
                    check=True,
                )

            # 2. Run OpenMX SCF calculation with node error monitoring
            node_error_detected = self._run_openmx_with_monitor(
                ctx.config.get("commands", {}).get("run_openmx", self.openmx_command),
                scf_dir,
                ctx,
            )

            if node_error_detected:
                if self.node_error_flag:
                    self.node_error_flag.touch()
                return TaskResult(
                    status=TaskStatus.FAILED,
                    errors=["Node error detected during SCF calculation"],
                    warnings=warnings,
                    metrics=metrics,
                )

            # 3. Post-process OpenMX output
            self._postprocess_openmx(scf_dir)

            # 4. Check SCF convergence
            check_cmd = ctx.config.get("commands", {}).get("check_conv")
            scf_converged = True
            if check_cmd:
                result = run_command_safe(
                    check_cmd,
                    args={"scf": str(scf_dir)},
                    cwd=scf_dir,
                    capture_output=True,
                )
                if "False" in result.stdout:
                    scf_converged = False
                    error_type = (
                        "scferror" if "scferror" in result.stdout else "sluerror"
                    )
                    errors.append(f"SCF did not converge: {error_type}")

            if not scf_converged:
                return TaskResult(
                    status=TaskStatus.FAILED,
                    output_path=None,
                    errors=errors,
                    warnings=warnings,
                    metrics=metrics,
                )

            # 5. Extract Hamiltonian
            extract_cmd = ctx.config.get("commands", {}).get("extract_hamiltonian")
            if extract_cmd:
                run_command_safe(
                    extract_cmd,
                    args={"scf": str(scf_dir)},
                    cwd=geth_dir,
                )

            # 6. Verify output
            hamiltonians_file = geth_dir / HAMILTONIAN_FILENAME
            if not hamiltonians_file.exists():
                errors.append(f"Output Hamiltonian not found: {hamiltonians_file}")
                return TaskResult(
                    status=TaskStatus.FAILED,
                    output_path=None,
                    errors=errors,
                    warnings=warnings,
                    metrics=metrics,
                )

            return TaskResult(
                status=TaskStatus.SUCCESS,
                output_path=hamiltonians_file,
                errors=errors,
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
        """Validate Calc execution result.

        Checks SCF convergence and output Hamiltonian integrity.

        Args:
            result: TaskResult to validate
            ctx: Execution context

        Returns:
            True if validation passed
        """
        if not result.output_path or not result.output_path.exists():
            result.add_error("Output file not found")
            return False

        workdir = Path(ctx.config.get("_workdir", ctx.workdir))
        scf_dir = Path(ctx.config.get("_scf_dir", workdir / SCF_SUBDIR))

        validation_passed = True

        # 1. Check SCF convergence
        scf_output = scf_dir / "openmx.out"
        if scf_output.exists():
            scf_validator = SCFConvergenceValidator()
            scf_result = scf_validator.validate(scf_output)

            if not scf_result.is_valid:
                for error in scf_result.errors:
                    result.add_error(f"SCF convergence: {error}")
                validation_passed = False

            for warning in scf_result.warnings:
                result.add_warning(f"SCF: {warning}")

            result.validation_results.append(scf_result)
        else:
            result.add_warning("SCF output file not found for convergence check")

        # 2. Check Hamiltonian HDF5 integrity
        ham_validator = HDF5IntegrityValidator()
        ham_result = ham_validator.validate(result.output_path)

        if not ham_result.is_valid:
            for error in ham_result.errors:
                result.add_error(f"Hamiltonian: {error}")
            validation_passed = False

        result.validation_results.append(ham_result)

        return validation_passed

    def cleanup(self, task: CalcTask, ctx: ExecutorContext) -> None:
        """Clean up after Calc execution.

        Removes temporary files while keeping outputs.

        Args:
            task: Task that was executed
            ctx: Execution context
        """
        workdir = ctx.config.get("_workdir")
        if workdir:
            cleanup_path = Path(workdir)
            if cleanup_path.exists() and cleanup_path.is_dir():
                try:
                    # Keep final Hamiltonian output
                    geth_dir = cleanup_path / GETH_SUBDIR
                    ham_file = geth_dir / HAMILTONIAN_FILENAME

                    # Remove SCF directory contents but keep structure
                    scf_dir = cleanup_path / SCF_SUBDIR
                    if scf_dir.exists():
                        for item in scf_dir.iterdir():
                            if item.is_file() and item.suffix in [".tmp", ".rst"]:
                                item.unlink()

                    # Optionally keep only essential outputs
                    # For now, we preserve the entire working directory
                    # Users can configure cleanup behavior if needed

                except Exception:
                    pass

    def _run_openmx_with_monitor(
        self,
        command_template: str,
        workdir: Path,
        ctx: ExecutorContext,
    ) -> bool:
        """Run OpenMX with node error monitoring.

        Args:
            command_template: Command template to execute
            workdir: Working directory
            ctx: Execution context

        Returns:
            True if node error detected, False otherwise
        """
        ntasks = self.num_cores // max(1, self.max_processes)
        command = safe_format_command(command_template, ntasks=ntasks)

        output_file = workdir / "openmx.std"
        node_error_detected = False

        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=open(output_file, "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(workdir),
        )

        def monitor_output():
            nonlocal node_error_detected
            with open(output_file, "r", encoding="utf-8") as f:
                while proc.poll() is None:
                    line = f.readline()
                    if not line:
                        continue
                    # Check for node errors
                    if "Requested nodes are busy" in line or "Socket timed out" in line:
                        node_error_detected = True
                        proc.terminate()
                        return

        monitor_thread = Thread(target=monitor_output, daemon=True)
        monitor_thread.start()
        proc.wait()
        monitor_thread.join()

        return node_error_detected

    def _postprocess_openmx(self, workdir: Path) -> None:
        """Post-process OpenMX output files.

        Appends openmx.out to openmx.scfout and cleans up restart directory.

        Args:
            workdir: SCF working directory
        """
        # Append openmx.out to openmx.scfout
        scfout_file = workdir / "openmx.scfout"
        openmx_out = workdir / "openmx.out"

        if openmx_out.exists():
            with open(scfout_file, "a", encoding="utf-8") as outf:
                with open(openmx_out, "r", encoding="utf-8") as inf:
                    outf.write(inf.read())

        # Clean up restart directory
        rst_dir = workdir / "openmx_rst"
        if rst_dir.exists():
            shutil.rmtree(rst_dir)
