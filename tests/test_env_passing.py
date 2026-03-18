"""Unit tests for environment variable passing in executors."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from dlazy.execution.olp_executor import OlpExecutor
from dlazy.execution.infer_executor import InferExecutor
from dlazy.execution.calc_executor import CalcExecutor
from dlazy.execution.base import ExecutorContext
from dlazy.core.tasks import OlpTask, InferTask, CalcTask


class TestOlpExecutorEnvPassing:
    """Test environment variable passing in OlpExecutor."""

    def test_olp_executor_passes_env_to_subprocess(self, tmp_path):
        """Test that OlpExecutor passes env to subprocess.run calls."""
        executor = OlpExecutor(openmx_command="echo test", num_cores=24, extract_command="echo extract")
        
        task = OlpTask(path="/path/to/POSCAR")
        ctx = ExecutorContext(
            config={
                "slurm": {
                    "env_vars": {
                        "OMP_NUM_THREADS": "24",
                        "CUSTOM_VAR": "custom_value",
                    }
                },
                "commands": {},
            },
            workdir=tmp_path,
            stage="olp",
        )
        
        captured_envs = []
        
        def capture_run(*args, **kwargs):
            if "env" in kwargs:
                captured_envs.append(kwargs["env"])
            return MagicMock(returncode=0, stdout="", stderr="")
        
        with patch.object(subprocess, "run", side_effect=capture_run):
            executor.execute(task, ctx)
        
        assert len(captured_envs) >= 2, "Should have captured at least 2 subprocess.run calls"
        for env in captured_envs:
            assert "CUSTOM_VAR" in env, "env should contain CUSTOM_VAR from slurm.env_vars"
            assert env["CUSTOM_VAR"] == "custom_value"

    def test_olp_executor_env_includes_os_environ(self, tmp_path):
        """Test that OlpExecutor env includes os.environ values."""
        os.environ["TEST_OLP_VAR"] = "test_olp_value"
        
        try:
            executor = OlpExecutor(openmx_command="echo test", num_cores=24)
            
            task = OlpTask(path="/path/to/POSCAR")
            ctx = ExecutorContext(
                config={"slurm": {"env_vars": {}}, "commands": {}},
                workdir=tmp_path,
                stage="olp",
            )
            
            captured_envs = []
            
            def capture_run(*args, **kwargs):
                if "env" in kwargs:
                    captured_envs.append(kwargs["env"])
                return MagicMock(returncode=0, stdout="", stderr="")
            
            with patch.object(subprocess, "run", side_effect=capture_run):
                executor.execute(task, ctx)
            
            for env in captured_envs:
                assert "TEST_OLP_VAR" in env, "env should contain os.environ values"
                assert env["TEST_OLP_VAR"] == "test_olp_value"
        finally:
            del os.environ["TEST_OLP_VAR"]


class TestInferExecutorEnvPassing:
    """Test environment variable passing in InferExecutor."""

    def test_infer_executor_passes_env_to_all_subprocesses(self, tmp_path):
        """Test that InferExecutor passes env to all subprocess.run calls."""
        workdir = tmp_path / "workdir"
        workdir.mkdir(parents=True, exist_ok=True)
        
        executor = InferExecutor(
            transform_command="echo transform",
            infer_command="echo infer",
            transform_reverse_command="echo reverse",
            model_dir=tmp_path / "model",
        )
        
        task = InferTask(path="/path/to/POSCAR", scf_path=str(tmp_path / "scf"))
        
        ctx = ExecutorContext(
            config={
                "slurm": {
                    "env_vars": {
                        "INFER_VAR": "infer_value",
                    }
                },
                "commands": {},
                "infer_template": None,
            },
            workdir=workdir,
            stage="infer",
        )
        ctx.config["_workdir"] = str(workdir)
        
        captured_envs = []
        
        def capture_run(*args, **kwargs):
            if "env" in kwargs:
                captured_envs.append(kwargs["env"])
            return MagicMock(returncode=0, stdout="", stderr="")
        
        with patch.object(subprocess, "run", side_effect=capture_run):
            with patch.object(executor, "_find_latest_output") as mock_find:
                mock_find.return_value = workdir / "outputs" / "output1"
                (workdir / "outputs" / "output1" / "dft" / "task.000000").mkdir(parents=True, exist_ok=True)
                (workdir / "outputs" / "output1" / "dft" / "task.000000" / "Hamil_pred.h5").touch()
                
                executor.execute(task, ctx)
        
        assert len(captured_envs) >= 2, "Should have captured at least 2 subprocess.run calls (transform, transform_reverse)"
        for env in captured_envs:
            assert "INFER_VAR" in env, "env should contain INFER_VAR from slurm.env_vars"


class TestCalcExecutorEnvPassing:
    """Test environment variable passing in CalcExecutor."""

    def test_calc_executor_passes_env_to_popen(self, tmp_path):
        """Test that CalcExecutor passes env to subprocess.Popen."""
        executor = CalcExecutor(openmx_command="echo test", num_cores=24)
        
        scf_dir = tmp_path / "scf"
        scf_dir.mkdir(parents=True, exist_ok=True)
        
        ctx = ExecutorContext(
            config={"slurm": {}, "commands": {}},
            workdir=tmp_path,
            stage="calc",
        )
        
        test_env = {"CALC_VAR": "calc_value"}
        
        captured_env = {}
        
        def capture_popen(*args, **kwargs):
            if "env" in kwargs:
                captured_env.update(kwargs["env"])
            mock_proc = MagicMock()
            mock_proc.poll.return_value = 0
            mock_proc.wait.return_value = None
            return mock_proc
        
        with patch.object(subprocess, "Popen", side_effect=capture_popen):
            executor._run_openmx_with_monitor("echo openmx", scf_dir, ctx, test_env)
        
        assert "CALC_VAR" in captured_env, "Popen should receive env parameter"

    def test_calc_executor_execute_passes_env(self, tmp_path):
        """Test that CalcExecutor.execute passes env to all commands."""
        executor = CalcExecutor(openmx_command="echo test", num_cores=24)
        
        task = CalcTask(path="/path/to/POSCAR", geth_path=str(tmp_path / "geth"))
        
        workdir = tmp_path / "workdir"
        scf_dir = workdir / "scf"
        geth_dir = workdir / "geth"
        scf_dir.mkdir(parents=True, exist_ok=True)
        geth_dir.mkdir(parents=True, exist_ok=True)
        
        ctx = ExecutorContext(
            config={
                "slurm": {
                    "env_vars": {
                        "CALC_TEST_VAR": "calc_test_value",
                    }
                },
                "commands": {
                    "create_infile": "echo create",
                    "check_conv": "echo True",
                    "extract_hamiltonian": "echo extract",
                },
            },
            workdir=workdir,
            stage="calc",
        )
        ctx.config["_workdir"] = str(workdir)
        ctx.config["_scf_dir"] = str(scf_dir)
        ctx.config["_geth_dir"] = str(geth_dir)
        
        captured_envs = []
        
        def capture_run_safe(*args, **kwargs):
            if "env" in kwargs:
                captured_envs.append(kwargs["env"])
            from subprocess import CompletedProcess
            return CompletedProcess(args=args, returncode=0, stdout="True", stderr="")
        
        with patch("dlazy.execution.calc_executor.run_command_safe", side_effect=capture_run_safe):
            with patch.object(executor, "_run_openmx_with_monitor") as mock_run:
                mock_run.return_value = False
                
                executor.execute(task, ctx)
        
        for env in captured_envs:
            assert "CALC_TEST_VAR" in env, "run_command_safe should receive env with CALC_TEST_VAR"


class TestEnvMerging:
    """Test env merging behavior."""

    def test_env_merging_combines_sources(self, tmp_path):
        """Test that env properly combines os.environ and slurm.env_vars."""
        os.environ["TEST_COMBINE_VAR"] = "os_value"
        
        try:
            executor = OlpExecutor(openmx_command="echo test", num_cores=24)
            
            task = OlpTask(path="/path/to/POSCAR")
            ctx = ExecutorContext(
                config={
                    "slurm": {
                        "env_vars": {
                            "TEST_SLURM_VAR": "slurm_value",
                        }
                    },
                    "commands": {},
                },
                workdir=tmp_path,
                stage="olp",
            )
            
            captured_envs = []
            
            def capture_run(*args, **kwargs):
                if "env" in kwargs:
                    captured_envs.append(kwargs["env"])
                return MagicMock(returncode=0, stdout="", stderr="")
            
            with patch.object(subprocess, "run", side_effect=capture_run):
                executor.execute(task, ctx)
            
            for env in captured_envs:
                assert "TEST_COMBINE_VAR" in env, "Should have os.environ var"
                assert env["TEST_COMBINE_VAR"] == "os_value"
                assert "TEST_SLURM_VAR" in env, "Should have slurm.env_vars"
                assert env["TEST_SLURM_VAR"] == "slurm_value"
        finally:
            del os.environ["TEST_COMBINE_VAR"]

    def test_slurm_vars_override_os_environ(self, tmp_path):
        """Test that slurm.env_vars override os.environ."""
        os.environ["OVERRIDE_VAR"] = "original"
        
        try:
            executor = OlpExecutor(openmx_command="echo test", num_cores=24)
            
            task = OlpTask(path="/path/to/POSCAR")
            ctx = ExecutorContext(
                config={
                    "slurm": {
                        "env_vars": {
                            "OVERRIDE_VAR": "overridden",
                        }
                    },
                    "commands": {},
                },
                workdir=tmp_path,
                stage="olp",
            )
            
            captured_envs = []
            
            def capture_run(*args, **kwargs):
                if "env" in kwargs:
                    captured_envs.append(kwargs["env"])
                return MagicMock(returncode=0, stdout="", stderr="")
            
            with patch.object(subprocess, "run", side_effect=capture_run):
                executor.execute(task, ctx)
            
            for env in captured_envs:
                assert env["OVERRIDE_VAR"] == "overridden", "slurm.env_vars should override"
        finally:
            del os.environ["OVERRIDE_VAR"]
