"""
性能优化测试

测试配置缓存、SLURM 缓存、文件操作优化等
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest


# ============================================================
# 配置缓存测试
# ============================================================


class TestConfigCache:
    """测试配置缓存功能"""

    def test_config_cache_hit(self, tmp_path):
        """测试配置缓存命中"""
        from dlazy.utils import load_yaml_config, _config_cache

        # 创建测试配置文件
        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: value\n")

        # 清空缓存
        _config_cache.clear()

        # 首次加载
        start = time.perf_counter()
        config1 = load_yaml_config(config_file, use_cache=True)
        first_time = time.perf_counter() - start

        # 缓存命中
        start = time.perf_counter()
        config2 = load_yaml_config(config_file, use_cache=True)
        cached_time = time.perf_counter() - start

        assert config1 == config2
        assert cached_time < first_time * 0.5  # 缓存应该更快

        # 检查缓存已填充
        cache_key = str(config_file.resolve())
        assert cache_key in _config_cache

    def test_config_cache_invalidation_on_mtime_change(self, tmp_path):
        """测试配置文件修改后缓存自动失效"""
        from dlazy.utils import load_yaml_config, _config_cache

        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: value1\n")

        # 首次加载
        config1 = load_yaml_config(config_file, use_cache=True)
        assert config1["key"] == "value1"

        # 修改文件（需要等待一段时间确保 mtime 变化）
        time.sleep(0.01)
        config_file.write_text("key: value2\n")

        # 应该重新加载
        config2 = load_yaml_config(config_file, use_cache=True)
        assert config2["key"] == "value2"

    def test_config_cache_disabled(self, tmp_path):
        """测试禁用缓存"""
        from dlazy.utils import load_yaml_config, _config_cache

        config_file = tmp_path / "config.yaml"
        config_file.write_text("key: value\n")

        _config_cache.clear()

        # 禁用缓存加载
        config1 = load_yaml_config(config_file, use_cache=False)

        # 检查缓存未填充
        cache_key = str(config_file.resolve())
        assert cache_key not in _config_cache

        # 再次加载
        config2 = load_yaml_config(config_file, use_cache=False)
        assert config1 == config2


# ============================================================
# SLURM 缓存测试
# ============================================================


class TestSlurmCache:
    """测试 SLURM 状态缓存"""

    def test_slurm_state_cache_hit(self):
        """测试 SLURM 状态缓存命中"""
        from dlazy.slurm_cache import SlurmStateCache

        cache = SlurmStateCache(default_ttl=10.0)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="COMPLETED\n")

            # 首次查询
            state1 = cache.get_job_state("12345")
            assert state1 == "COMPLETED"
            assert mock_run.call_count == 1

            # 缓存命中
            state2 = cache.get_job_state("12345")
            assert state2 == "COMPLETED"
            assert mock_run.call_count == 1  # 未增加调用次数

    def test_slurm_state_cache_expiration(self):
        """测试 SLURM 状态缓存过期"""
        from dlazy.slurm_cache import SlurmStateCache

        cache = SlurmStateCache(default_ttl=0.1)  # 100ms TTL

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="RUNNING\n")

            # 首次查询
            state1 = cache.get_job_state("12345")
            assert state1 == "RUNNING"

            # 等待过期
            time.sleep(0.15)

            # 应该重新查询
            mock_run.return_value.stdout = "COMPLETED\n"
            state2 = cache.get_job_state("12345")
            assert state2 == "COMPLETED"
            assert mock_run.call_count == 2

    def test_batch_check_states(self):
        """测试批量查询优化"""
        from dlazy.slurm_cache import SlurmStateCache

        cache = SlurmStateCache()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="12345 COMPLETED\n12346 RUNNING\n12347 PENDING\n"
            )

            job_ids = ["12345", "12346", "12347"]
            states = cache.batch_check_states(job_ids)

            # 应该只调用一次 sacct
            assert mock_run.call_count == 1
            assert len(states) == 3
            assert states["12345"] == "COMPLETED"
            assert states["12346"] == "RUNNING"
            assert states["12347"] == "PENDING"

    def test_running_jobs_cache(self):
        """测试运行中作业缓存"""
        from dlazy.slurm_cache import SlurmStateCache

        cache = SlurmStateCache()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="12345\n12346\n")

            with patch.dict(os.environ, {"USER": "testuser"}):
                # 首次查询
                jobs1 = cache.get_running_jobs("0olp")
                assert len(jobs1) == 2
                assert mock_run.call_count == 1

                # 缓存命中
                jobs2 = cache.get_running_jobs("0olp")
                assert len(jobs2) == 2
                assert mock_run.call_count == 1

    def test_cache_invalidation(self):
        """测试缓存手动失效"""
        from dlazy.slurm_cache import SlurmStateCache

        cache = SlurmStateCache()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="RUNNING\n")

            # 查询并缓存
            state1 = cache.get_job_state("12345")
            assert state1 == "RUNNING"

            # 手动失效
            cache.invalidate("12345")

            # 应该重新查询
            mock_run.return_value.stdout = "COMPLETED\n"
            state2 = cache.get_job_state("12345")
            assert state2 == "COMPLETED"
            assert mock_run.call_count == 2


# ============================================================
# 文件操作优化测试
# ============================================================


class TestOptimizedFileOperations:
    """测试优化的文件操作"""

    def test_should_relink_new_target(self, tmp_path):
        """测试新目标需要链接"""
        from dlazy.optimized_commands import _should_relink

        source = tmp_path / "source.txt"
        source.write_text("content")

        target = tmp_path / "target.txt"

        # 新目标需要链接
        assert _should_relink(source, target) is True

    def test_should_relink_correct_existing_link(self, tmp_path):
        """测试已存在的正确链接"""
        from dlazy.optimized_commands import _should_relink

        source = tmp_path / "source.txt"
        source.write_text("content")

        target = tmp_path / "target.txt"
        target.symlink_to(source)

        # 正确的链接，不需要重新链接
        assert _should_relink(source, target) is False

    def test_should_relink_wrong_target(self, tmp_path):
        """测试指向错误目标的链接"""
        from dlazy.optimized_commands import _should_relink

        source1 = tmp_path / "source1.txt"
        source1.write_text("content1")

        source2 = tmp_path / "source2.txt"
        source2.write_text("content2")

        target = tmp_path / "target.txt"
        target.symlink_to(source1)

        # 指向错误目标，需要重新链接
        assert _should_relink(source2, target) is True

    def test_smart_ensure_symlink_creates_new(self, tmp_path):
        """测试创建新链接"""
        from dlazy.optimized_commands import _smart_ensure_symlink

        source = tmp_path / "source.txt"
        source.write_text("content")

        target = tmp_path / "target.txt"

        # 创建新链接
        result = _smart_ensure_symlink(source, target)

        assert result is True
        assert target.is_symlink()
        assert target.resolve() == source.resolve()

    def test_smart_ensure_symlink_skips_correct(self, tmp_path):
        """测试跳过正确的链接"""
        from dlazy.optimized_commands import _smart_ensure_symlink

        source = tmp_path / "source.txt"
        source.write_text("content")

        target = tmp_path / "target.txt"
        target.symlink_to(source)

        # 正确的链接，应该跳过
        result = _smart_ensure_symlink(source, target)

        assert result is False

    def test_smart_ensure_symlink_updates_wrong(self, tmp_path):
        """测试更新错误的链接"""
        from dlazy.optimized_commands import _smart_ensure_symlink

        source1 = tmp_path / "source1.txt"
        source1.write_text("content1")

        source2 = tmp_path / "source2.txt"
        source2.write_text("content2")

        target = tmp_path / "target.txt"
        target.symlink_to(source1)

        # 更新链接
        result = _smart_ensure_symlink(source2, target)

        assert result is True
        assert target.resolve() == source2.resolve()

    def test_batch_smart_symlink(self, tmp_path):
        """测试批量创建链接"""
        from dlazy.optimized_commands import _batch_smart_symlink

        sources_targets = []
        for i in range(10):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content{i}")
            target = tmp_path / "links" / f"target{i}.txt"
            sources_targets.append((source, target))

        # 批量创建
        stats = _batch_smart_symlink(sources_targets)

        assert stats["created"] == 10
        assert stats["skipped"] == 0
        assert stats["failed"] == 0

        # 再次执行，应该跳过
        stats = _batch_smart_symlink(sources_targets)

        assert stats["created"] == 0
        assert stats["skipped"] == 10
        assert stats["failed"] == 0

    def test_ensure_clean_directory_new(self, tmp_path):
        """测试创建新目录"""
        from dlazy.optimized_commands import _ensure_clean_directory

        new_dir = tmp_path / "new_dir"

        _ensure_clean_directory(new_dir)

        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_ensure_clean_directory_force(self, tmp_path):
        """测试强制清理目录"""
        from dlazy.optimized_commands import _ensure_clean_directory

        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        (existing_dir / "file.txt").write_text("content")

        _ensure_clean_directory(existing_dir, force=True)

        assert existing_dir.exists()
        assert not (existing_dir / "file.txt").exists()

    def test_ensure_clean_directory_preserves_allowed(self, tmp_path):
        """测试保留允许的文件"""
        from dlazy.optimized_commands import _ensure_clean_directory

        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        (existing_dir / ".gitkeep").write_text("")
        (existing_dir / "README.md").write_text("readme")

        _ensure_clean_directory(existing_dir, force=False)

        assert existing_dir.exists()
        assert (existing_dir / ".gitkeep").exists()
        assert (existing_dir / "README.md").exists()


# ============================================================
# 性能监控测试
# ============================================================


class TestPerformanceMonitor:
    """测试性能监控"""

    def test_performance_monitor_context(self):
        """测试性能监控上下文管理器"""
        from dlazy.performance import PerformanceMonitor

        with PerformanceMonitor("test_operation", threshold_ms=1.0) as monitor:
            time.sleep(0.01)

        assert monitor.elapsed_ms >= 10.0

    def test_performance_monitor_decorator(self):
        """测试性能监控装饰器"""
        from dlazy.performance import PerformanceMonitor

        @PerformanceMonitor.track(threshold_ms=1.0)
        def slow_function():
            time.sleep(0.01)
            return "result"

        result = slow_function()

        assert result == "result"

        # 检查统计已记录
        stats = PerformanceMonitor.get_stats()
        assert any("slow_function" in k for k in stats.keys())

    def test_performance_stats_collection(self):
        """测试性能统计收集"""
        from dlazy.performance import PerformanceMonitor, track_performance

        PerformanceMonitor.reset_stats()

        # 执行多次操作
        for _ in range(5):
            with track_performance("test_op", threshold_ms=1000.0):
                time.sleep(0.01)

        stats = PerformanceMonitor.get_stats()

        assert "test_op" in stats
        assert stats["test_op"]["count"] == 5
        assert stats["test_op"]["total_ms"] >= 50.0

    def test_performance_summary(self, capsys):
        """测试性能摘要输出"""
        from dlazy.performance import PerformanceMonitor, track_performance

        PerformanceMonitor.reset_stats()

        for _ in range(3):
            with track_performance("operation_a", threshold_ms=1000.0):
                time.sleep(0.01)

        PerformanceMonitor.print_summary()

        captured = capsys.readouterr()
        assert "Performance Summary" in captured.out
        assert "operation_a" in captured.out


# ============================================================
# 性能基准测试
# ============================================================


class TestPerformanceBenchmarks:
    """性能基准测试"""

    def test_config_loading_benchmark(self, tmp_path, benchmark):
        """配置加载性能基准"""
        from dlazy.utils import load_yaml_config

        # 创建测试配置文件
        config_file = tmp_path / "config.yaml"
        config_data = {"key" + str(i): "value" + str(i) for i in range(100)}

        import yaml

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # 基准测试
        def load_cached():
            return load_yaml_config(config_file, use_cache=True)

        result = benchmark(load_cached)

        assert result == config_data

    def test_symlink_benchmark(self, tmp_path, benchmark):
        """符号链接操作性能基准"""
        from dlazy.optimized_commands import _smart_ensure_symlink

        sources_targets = []
        for i in range(100):
            source = tmp_path / f"source{i}.txt"
            source.write_text(f"content{i}")
            target = tmp_path / "links" / f"target{i}.txt"
            sources_targets.append((source, target))

        def create_links():
            for source, target in sources_targets:
                _smart_ensure_symlink(source, target)

        benchmark(create_links)

    def test_slurm_cache_benchmark(self, benchmark):
        """SLURM 缓存性能基准"""
        from dlazy.slurm_cache import SlurmStateCache

        cache = SlurmStateCache(default_ttl=60.0)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="RUNNING\n")

            # 首次查询填充缓存
            cache.get_job_state("12345")

            def cached_query():
                return cache.get_job_state("12345")

            result = benchmark(cached_query)

            assert result == "RUNNING"
            # 应该只有 1 次真实调用
            assert mock_run.call_count == 1


# ============================================================
# 集成测试
# ============================================================


class TestIntegration:
    """集成测试"""

    def test_full_workflow_with_optimizations(self, tmp_path):
        """测试完整工作流与优化"""
        from dlazy.utils import load_yaml_config, _config_cache
        from dlazy.slurm_cache import get_slurm_cache, SlurmStateCache
        from dlazy.optimized_commands import (
            _smart_ensure_symlink,
            _ensure_clean_directory,
        )
        from dlazy.performance import PerformanceMonitor, track_performance

        # 清空状态
        _config_cache.clear()
        cache = SlurmStateCache()
        cache.invalidate()
        PerformanceMonitor.reset_stats()

        # 1. 配置加载
        config_file = tmp_path / "config.yaml"
        config_file.write_text("stage:\n  param: value\n")

        with track_performance("config_load"):
            config = load_yaml_config(config_file)

        # 2. 目录操作
        work_dir = tmp_path / "work"
        _ensure_clean_directory(work_dir)

        # 3. 文件链接
        source = tmp_path / "source.txt"
        source.write_text("content")
        target = work_dir / "target.txt"

        with track_performance("file_link"):
            _smart_ensure_symlink(source, target)

        # 4. SLURM 状态查询
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="RUNNING\n")

            with track_performance("slurm_query"):
                state = cache.get_job_state("12345")

        # 验证结果
        assert config["stage"]["param"] == "value"
        assert target.exists()
        assert state == "RUNNING"

        # 检查性能统计
        stats = PerformanceMonitor.get_stats()
        assert "config_load" in stats
        assert "file_link" in stats
        assert "slurm_query" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--benchmark-only"])
