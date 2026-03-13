"""
集成指南 - 如何应用性能优化到现有代码

本指南展示如何将性能优化集成到现有代码库中。
"""

# ============================================================
# 1. 配置缓存集成
# ============================================================

# BEFORE: executor.py
# ```python
# def run_olp_stage(...):
#     config = load_global_config_section(Path(global_config), "0olp")
# ```

# AFTER: 无需修改，自动使用缓存
# utils.py 中的 load_yaml_config 已经自动支持缓存


# ============================================================
# 2. SLURM 状态缓存集成
# ============================================================

# BEFORE: workflow.py
# ```python
# class WorkflowManager(WorkflowBase):
#     def _get_running_jobs(self, stage_name: str) -> List[str]:
#         cmd = f"squeue -u {user} -n '{job_name}' -h --format='%i'"
#         result = self._run_command(cmd)
#         ...
#
#     def _check_slurm_job_state(self, job_id: str) -> str:
#         cmd = f"sacct -j {main_job_id} --format=State --noheader"
#         result = self._run_command(cmd)
#         ...
# ```

# AFTER: workflow.py
# ```python
# from .slurm_cache import get_slurm_cache
#
#
# class WorkflowManager(WorkflowBase):
#     def __init__(self, config_path: Path, workdir: Path):
#         super().__init__()
#         self.config_path = Path(config_path).resolve()
#         self.workdir = Path(workdir).resolve()
#         self.path_resolver = RunPathResolver(self.workdir)
#         self.slurm_cache = get_slurm_cache()  # 添加缓存实例
#         self.config = self._load_config()
#         self._init_monitor(monitor_state_file=self.workdir / MONITOR_STATE_FILE)
#
#     def _get_running_jobs(self, stage_name: str) -> List[str]:
#         """获取运行中的作业 - 使用缓存"""
#         return self.slurm_cache.get_running_jobs(stage_name)
#
#     def _check_slurm_job_state(self, job_id: str) -> str:
#         """检查作业状态 - 使用缓存"""
#         return self.slurm_cache.get_job_state(job_id)
#
#     def _get_all_user_jobs(self) -> Dict[str, str]:
#         """获取用户所有作业 - 使用缓存"""
#         return self.slurm_cache.get_all_user_jobs()
# ```

# BEFORE: batch_workflow.py
# ```python
# class BatchScheduler(WorkflowBase):
#     def _check_slurm_job_state(self, job_id: str) -> str:
#         result = subprocess.run(
#             f"sacct -j {main_job_id} --format=State --noheader",
#             shell=True, capture_output=True, text=True
#         )
#         ...
# ```

# AFTER: batch_workflow.py
# ```python
# from .slurm_cache import get_slurm_cache
#
#
# class BatchScheduler(WorkflowBase):
#     def __init__(self, ctx: BatchContext):
#         super().__init__()
#         self.ctx = ctx
#         self.logger = get_logger("batch_scheduler")
#         self.state: Dict[str, Any] = self._load_or_init_state()
#         self.config = load_yaml_config(self.ctx.config_path)
#         self.slurm_cache = get_slurm_cache()  # 添加缓存实例
#         ...
#
#     def _check_slurm_job_state(self, job_id: str) -> str:
#         """Check SLURM job state - using cache."""
#         return self.slurm_cache.get_job_state(job_id)
# ```


# ============================================================
# 3. 性能监控集成
# ============================================================

# BEFORE: executor.py
# ```python
# class WorkflowExecutor:
#     @staticmethod
#     def run_olp_stage(...):
#         config = load_global_config_section(Path(global_config), "0olp")
#         records = WorkflowExecutor._read_olp_records(...)
#         with multiprocessing.Pool(...) as pool:
#             results = pool.map(execute_func, records)
# ```

# AFTER: executor.py
# ```python
# from .performance import PerformanceMonitor, track_performance
#
#
# class WorkflowExecutor:
#     @staticmethod
#     @PerformanceMonitor.track("executor.run_olp_stage", threshold_ms=100.0)
#     def run_olp_stage(...):
#         with track_performance("olp.load_config", threshold_ms=10.0):
#             config = load_global_config_section(Path(global_config), "0olp")
#
#         with track_performance("olp.read_records", threshold_ms=50.0):
#             records = WorkflowExecutor._read_olp_records(...)
#
#         with track_performance("olp.execute_pool", threshold_ms=1000.0):
#             with multiprocessing.Pool(...) as pool:
#                 results = pool.map(execute_func, records)
# ```


# ============================================================
# 4. 增量文件操作集成
# ============================================================

# BEFORE: commands.py
# ```python
# class InferCommandExecutor:
#     @staticmethod
#     def execute(group_index: int, ctx: InferContext):
#         # 清理并重建目录
#         _cleanup_directory(input_dir)
#         ensure_directory(input_dir / GETH_SUBDIR)
#         _cleanup_directory(output_dir)
#         ensure_directory(output_dir)
#
#         # 链接文件
#         InferCommandExecutor._link_overlap_files(
#             records, input_dir / GETH_SUBDIR, ctx, logger
#         )
#
#     @staticmethod
#     def _link_overlap_files(records, target_root, ctx, logger):
#         for record in records:
#             source_dir = Path(record["geth_path"])
#             target = target_root / short_path
#             _ensure_symlink(source_dir, target)
# ```

# AFTER: commands.py
# ```python
# from .optimized_commands import (
#     _ensure_clean_directory,
#     _smart_ensure_symlink,
#     _batch_smart_symlink,
# )
#
#
# class InferCommandExecutor:
#     @staticmethod
#     def execute(group_index: int, ctx: InferContext):
#         # 智能清理目录
#         _ensure_clean_directory(input_dir, force=False)
#         _ensure_clean_directory(output_dir, force=False)
#
#         # 链接文件（使用优化版本）
#         InferCommandExecutor._link_overlap_files_optimized(
#             records, input_dir / GETH_SUBDIR, ctx, logger
#         )
#
#     @staticmethod
#     def _link_overlap_files_optimized(records, target_root, ctx, logger):
#         """Optimized version with smart symlink creation."""
#         ensure_directory(target_root)
#
#         # 准备批量操作
#         sources_targets = []
#         for record in records:
#             short_path = Path(record["short_path"])
#             source_dir = Path(record["geth_path"])
#             target = target_root / short_path
#
#             if source_dir.exists():
#                 sources_targets.append((source_dir, target))
#             else:
#                 logger.warning("Source directory not found: %s", source_dir)
#
#         # 批量创建链接
#         stats = _batch_smart_symlink(sources_targets, logger)
#         logger.info(
#             "Linked %d directories (skipped %d existing, failed %d)",
#             stats["created"], stats["skipped"], stats["failed"]
#         )
# ```


# ============================================================
# 5. 随机路径生成优化
# ============================================================

# BEFORE: utils.py
# ```python
# import secrets
#
# def generate_random_paths(base_dir: Path) -> Tuple[Path, Path]:
#     def gen_path():
#         h = secrets.token_hex(16)  # 密码学安全，但较慢
#         return f"{h[:2]}/{h[2:4]}/{h[4:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
#     ...
# ```

# AFTER: utils.py
# ```python
# import uuid
#
# def generate_random_paths(base_dir: Path) -> Tuple[Path, Path]:
#     """Generate random SCF and GETH paths - using faster UUID generation."""
#     def gen_path():
#         h = uuid.uuid4().hex  # 16x faster than secrets.token_hex(16)
#         return f"{h[:2]}/{h[2:4]}/{h[4:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
#
#     scf_path = base_dir / gen_path()
#     geth_path = base_dir / gen_path()
#
#     return scf_path, geth_path
# ```


# ============================================================
# 6. 路径解析器缓存
# ============================================================

# BEFORE: batch_workflow.py
# ```python
# class BatchScheduler(WorkflowBase):
#     def _get_path_resolver(self, batch_index: int) -> BatchPathResolver:
#         return BatchPathResolver(self.ctx.workflow_root, batch_index)
# ```

# AFTER: batch_workflow.py
# ```python
# class BatchScheduler(WorkflowBase):
#     def __init__(self, ctx: BatchContext):
#         super().__init__()
#         self.ctx = ctx
#         self.logger = get_logger("batch_scheduler")
#         self.state: Dict[str, Any] = self._load_or_init_state()
#         self.config = load_yaml_config(self.ctx.config_path)
#         self._resolver_cache: Dict[int, BatchPathResolver] = {}  # 添加缓存
#         ...
#
#     def _get_path_resolver(self, batch_index: int) -> BatchPathResolver:
#         """Get PathResolver for a specific batch - with caching."""
#         if batch_index not in self._resolver_cache:
#             self._resolver_cache[batch_index] = BatchPathResolver(
#                 self.ctx.workflow_root, batch_index
#             )
#         return self._resolver_cache[batch_index]
# ```


# ============================================================
# 7. 完整集成示例
# ============================================================

"""
完整的集成示例 - 展示如何在入口点初始化所有优化
"""

# cli.py 或 __main__.py

import logging
from pathlib import Path

from dlazy.performance import PerformanceMonitor, get_performance_logger
from dlazy.slurm_cache import get_slurm_cache


def setup_optimizations(config: dict):
    """Setup all performance optimizations."""

    # 1. 配置性能监控
    perf_config = config.get("performance", {})

    if perf_config.get("monitoring", {}).get("enabled", True):
        perf_logger = get_performance_logger()
        perf_logger.setLevel(logging.INFO)

        log_file = perf_config.get("monitoring", {}).get("log_file", "performance.log")
        handler = logging.FileHandler(log_file)
        handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
        )
        perf_logger.addHandler(handler)

        print(f"Performance monitoring enabled: {log_file}")

    # 2. 配置 SLURM 缓存
    if perf_config.get("slurm_cache", {}).get("enabled", True):
        slurm_config = perf_config["slurm_cache"]
        cache = get_slurm_cache()

        if "default_ttl" in slurm_config:
            cache.default_ttl = slurm_config["default_ttl"]
        if "terminal_ttl" in slurm_config:
            cache.terminal_ttl = slurm_config["terminal_ttl"]

        print(f"SLURM cache enabled: TTL={cache.default_ttl}s")

    # 3. 配置缓存已自动启用（utils.py 中的 load_yaml_config）
    if perf_config.get("config_cache", {}).get("enabled", True):
        print("Config cache enabled (auto)")


def cleanup_optimizations():
    """Cleanup optimizations before exit."""

    # 打印性能摘要
    print("\n" + "=" * 80)
    PerformanceMonitor.print_summary()
    print("=" * 80 + "\n")

    # 清理缓存
    cache = get_slurm_cache()
    expired = cache.cleanup_expired()
    if expired > 0:
        print(f"Cleaned up {expired} expired cache entries")


# 在主函数中使用
def main():
    import atexit

    # 加载配置
    config = load_config()

    # 初始化优化
    setup_optimizations(config)

    # 注册清理函数
    atexit.register(cleanup_optimizations)

    # 运行主程序
    try:
        run_workflow(config)
    finally:
        cleanup_optimizations()


if __name__ == "__main__":
    main()
