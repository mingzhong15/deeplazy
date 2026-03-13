#!/usr/bin/env python3
"""测试资源管理器模块"""

import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from dlazy.resource_manager import (
    ResourceManager,
    managed_process,
    run_monitored_process,
    safe_chdir,
    safe_file,
)


class TestSafeFile:
    def test_file_closed_after_context(self):
        """测试文件在上下文退出后正确关闭"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with safe_file(tmp_path, "w") as f:
                f.write("test content")
                assert not f.closed

            assert f.closed
            content = tmp_path.read_text()
            assert content == "test content"
        finally:
            tmp_path.unlink()

    def test_file_closed_on_exception(self):
        """测试异常时文件正确关闭"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            try:
                with safe_file(tmp_path, "w") as f:
                    f.write("before exception")
                    raise ValueError("test error")
            except ValueError:
                pass

            assert f.closed
            assert tmp_path.read_text() == "before exception"
        finally:
            tmp_path.unlink()

    def test_write_and_read_modes(self):
        """测试不同模式"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with safe_file(tmp_path, "w") as f:
                f.write("hello world")

            with safe_file(tmp_path, "r") as f:
                content = f.read()

            assert content == "hello world"
        finally:
            tmp_path.unlink()


class TestSafeChdir:
    def test_restore_original_dir(self):
        """测试退出时恢复原目录"""
        original_dir = Path.cwd()

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)
            with safe_chdir(target_dir):
                assert Path.cwd() == target_dir

            assert Path.cwd() == original_dir

    def test_restore_on_exception(self):
        """测试异常时恢复原目录"""
        original_dir = Path.cwd()

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)
            try:
                with safe_chdir(target_dir):
                    assert Path.cwd() == target_dir
                    raise ValueError("test error")
            except ValueError:
                pass

            assert Path.cwd() == original_dir

    def test_nested_chdir(self):
        """测试嵌套目录切换"""
        original_dir = Path.cwd()

        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                dir1 = Path(tmpdir1)
                dir2 = Path(tmpdir2)

                with safe_chdir(dir1):
                    assert Path.cwd() == dir1
                    with safe_chdir(dir2):
                        assert Path.cwd() == dir2
                    assert Path.cwd() == dir1
                assert Path.cwd() == original_dir


class TestRunMonitoredProcess:
    def test_normal_completion(self):
        """测试正常完成"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "output.txt"
            error_patterns = ["ERROR", "FAILED"]

            error_detected, returncode = run_monitored_process(
                command="echo 'hello world'",
                stdout_path=stdout_path,
                error_patterns=error_patterns,
                check_interval=0.1,
            )

            assert error_detected is False
            assert returncode == 0
            assert "hello world" in stdout_path.read_text()

    def test_error_pattern_detection(self):
        """测试错误模式检测"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "output.txt"
            error_patterns = ["Requested nodes are busy", "Socket timed out"]

            error_detected, returncode = run_monitored_process(
                command="echo 'Requested nodes are busy' && sleep 5",
                stdout_path=stdout_path,
                error_patterns=error_patterns,
                check_interval=0.1,
            )

            assert error_detected is True

    def test_timeout_handling(self):
        """测试超时处理"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "output.txt"
            error_patterns = []

            error_detected, returncode = run_monitored_process(
                command="sleep 10",
                stdout_path=stdout_path,
                error_patterns=error_patterns,
                check_interval=0.1,
                timeout=0.5,
            )

            assert returncode == -1

    def test_with_cwd(self):
        """测试指定工作目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            work_dir = Path(tmpdir) / "work"
            work_dir.mkdir()
            stdout_path = Path(tmpdir) / "output.txt"
            error_patterns = []

            run_monitored_process(
                command="pwd > /dev/null",
                stdout_path=stdout_path,
                error_patterns=error_patterns,
                check_interval=0.1,
                cwd=work_dir,
            )

    def test_with_env(self):
        """测试环境变量传递"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "output.txt"
            error_patterns = []

            env = os.environ.copy()
            env["MY_TEST_VAR"] = "test_value_123"

            run_monitored_process(
                command='echo "$MY_TEST_VAR"',
                stdout_path=stdout_path,
                error_patterns=error_patterns,
                check_interval=0.1,
                env=env,
            )

            content = stdout_path.read_text()
            assert "test_value_123" in content


class TestResourceManager:
    def test_open_file_tracking(self):
        """测试文件打开跟踪"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            manager = ResourceManager()
            with manager.open_file(tmp_path, "w") as f:
                f.write("test")
                assert len(manager._open_files) == 1

            assert len(manager._open_files) == 0
            assert f.closed
        finally:
            tmp_path.unlink()

    def test_cleanup_closes_files(self):
        """测试 cleanup 关闭所有文件"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            manager = ResourceManager()
            f = None

            with manager.open_file(tmp_path, "w") as f:
                f.write("test")

            manager._open_files.append((tmp_path, open(tmp_path, "w")))
            assert len(manager._open_files) == 1

            manager.cleanup()

            assert len(manager._open_files) == 0
        finally:
            tmp_path.unlink()

    def test_chdir_tracking(self):
        """测试目录切换跟踪"""
        original_dir = Path.cwd()

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)
            manager = ResourceManager()

            with manager.chdir(target_dir):
                assert Path.cwd() == target_dir

            assert Path.cwd() == original_dir

    def test_context_manager(self):
        """测试上下文管理器模式"""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            with ResourceManager() as manager:
                with manager.open_file(tmp_path, "w") as f:
                    f.write("test")

            assert len(manager._open_files) == 0
        finally:
            tmp_path.unlink()


class TestManagedProcess:
    def test_normal_execution(self):
        """测试正常执行"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "output.txt"

            with managed_process(
                command="echo 'hello'",
                stdout_path=stdout_path,
            ) as proc:
                proc.wait()

            assert proc.returncode == 0
            assert "hello" in stdout_path.read_text()

    def test_terminate_on_exit(self):
        """测试退出时终止进程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "output.txt"

            with managed_process(
                command="sleep 100",
                stdout_path=stdout_path,
            ) as proc:
                pass

            assert proc.poll() is not None

    def test_file_closed_on_exit(self):
        """测试退出时关闭文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "output.txt"

            stdout_f = None
            with managed_process(
                command="echo 'test'",
                stdout_path=stdout_path,
            ) as proc:
                proc.wait()
                stdout_f = proc.stdout

            if stdout_f and hasattr(stdout_f, "closed"):
                assert stdout_f.closed


class TestEdgeCases:
    def test_safe_file_nonexistent_path(self):
        """测试不存在的路径读取"""
        with pytest.raises(FileNotFoundError):
            with safe_file(Path("/nonexistent/path/file.txt"), "r") as f:
                pass

    def test_safe_chdir_nonexistent_dir(self):
        """测试切换到不存在的目录"""
        with pytest.raises(FileNotFoundError):
            with safe_chdir(Path("/nonexistent/directory")):
                pass

    def test_empty_error_patterns(self):
        """测试空错误模式列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            stdout_path = Path(tmpdir) / "output.txt"

            error_detected, returncode = run_monitored_process(
                command="echo 'any output'",
                stdout_path=stdout_path,
                error_patterns=[],
                check_interval=0.1,
            )

            assert error_detected is False
            assert returncode == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
