"""工作流执行器 - 统一入口"""

from __future__ import annotations

import json
import multiprocessing
import secrets
import shutil
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from .commands import CalcCommandExecutor, InferCommandExecutor, OLPCommandExecutor
from .constants import (
    ERROR_FILE,
    FOLDERS_FILE,
    GROUP_INFO_FILE,
    HAMLOG_FILE,
    PROGRESS_FILE,
)
from .contexts import CalcContext, InferContext, OLPContext
from .path_resolver import BatchPathResolver, PathResolver, RunPathResolver
from .core.exceptions import AbortException, FailureType, NodeError
from .utils import (
    get_logger,
    get_result_geth_dir,
    get_result_infer_dir,
    get_result_olp_dir,
    get_workflow_root,
    load_global_config_section,
)

# New execution module imports
from dlazy.execution import (
    create_executor,
    Executor,
    ExecutorContext,
    TaskResult,
    TaskStatus,
)
from dlazy.scheduler import JobManager, SlurmScheduler, SubmitConfig
from dlazy.state import CheckpointManager, TaskStateStore
from dlazy.core.tasks import OlpTask, InferTask, CalcTask

if TYPE_CHECKING:
    from .core.workflow_state import JobMonitor, TaskError


class WorkflowExecutor:
    """工作流执行器 - 封装三阶段逻辑"""

    @staticmethod
    def _detect_slurm() -> bool:
        """Detect if SLURM scheduler is available."""
        return shutil.which("sbatch") is not None

    @staticmethod
    def _create_olp_executor_context(ctx: OLPContext) -> ExecutorContext:
        return ExecutorContext(
            config=ctx.config,
            workdir=ctx.result_dir,
            stage="olp",
            monitor=ctx.monitor,
        )

    @staticmethod
    def _create_infer_executor_context(ctx: InferContext) -> ExecutorContext:
        return ExecutorContext(
            config=ctx.config,
            workdir=ctx.result_dir,
            stage="infer",
            monitor=ctx.monitor,
        )

    @staticmethod
    def _create_calc_executor_context(ctx: CalcContext) -> ExecutorContext:
        return ExecutorContext(
            config=ctx.config,
            workdir=ctx.result_dir,
            stage="calc",
            monitor=ctx.monitor,
        )

    # ==================== OLP 阶段 ====================

    @staticmethod
    def run_olp_stage(
        global_config: str,
        start: int,
        end: int,
        path_resolver: Optional[PathResolver] = None,
        workdir: Optional[str] = None,
        stru_log: Optional[str] = None,
        monitor: Optional[JobMonitor] = None,
        batch_index: Optional[int] = None,
        use_new_executor: bool = False,
    ) -> Dict[str, int]:
        """
        执行 OLP 阶段

        Args:
            global_config: 全局配置文件路径
            start: 起始索引
            end: 结束索引
            path_resolver: 路径解析器（用于run/batch模式统一）
            workdir: 工作目录（默认当前目录）
            stru_log: 结构列表文件（覆盖配置）
            monitor: 作业监控器
            batch_index: batch索引（batch模式）
            use_new_executor: 使用新执行器架构（默认False，安全回滚）

        Returns:
            {'success': N, 'failed': M, 'skipped': K}

        Raises:
            ConfigError: 配置错误
            NodeError: 节点错误（需要重算）
            AbortException: 快速失败
        """
        logger = get_logger("executor.olp")
        logger.info("run_olp_stage: start=%d, end=%d", start, end)

        config = load_global_config_section(Path(global_config), "0olp")

        if path_resolver is None:
            if batch_index is not None:
                workflow_root = Path(workdir) if workdir else Path.cwd()
                path_resolver = BatchPathResolver(workflow_root, batch_index)
            else:
                path_resolver = RunPathResolver(
                    Path(workdir) if workdir else Path.cwd()
                )

        workflow_root = path_resolver.get_workdir()
        result_dir = path_resolver.get_olp_output_dir()

        ctx = OLPContext(
            config=config,
            workflow_root=workflow_root,
            workdir=path_resolver.get_workdir(),
            result_dir=result_dir,
            progress_file=path_resolver.get_olp_progress_file(),
            folders_file=path_resolver.get_olp_folders_file(),
            error_file=path_resolver.get_olp_error_file(),
            num_cores=config.get("num_cores", 56),
            max_processes=config.get("max_processes", 7),
            node_error_flag=path_resolver.get_workdir()
            / f".node_error_flag-{secrets.token_hex(4)}",
            stru_log=Path(stru_log) if stru_log else None,
            monitor=monitor,
        )

        records = WorkflowExecutor._read_olp_records(ctx, start, end, path_resolver)
        logger.info("读取到 %d 条记录", len(records))

        if use_new_executor:
            results = WorkflowExecutor._run_olp_with_new_executor(ctx, records, logger)
        else:
            results = WorkflowExecutor._run_olp_legacy(ctx, records)

        if monitor:
            from .core.workflow_state import TaskError

            for status, label in results:
                if status in ["failed", "node_error"]:
                    ftype = (
                        FailureType.NODE_ERROR
                        if status == "node_error"
                        else FailureType.CALC_ERROR
                    )
                    monitor.report_error(
                        TaskError(
                            stage="0olp",
                            failure_type=ftype,
                            message=label,
                            timestamp=datetime.now(),
                        )
                    )

            if monitor.should_abort():
                raise AbortException(monitor.state.abort_reason or "Abort requested")

        stats = WorkflowExecutor._summarize_results(results)
        logger.info("run_olp_stage 完成: %s", stats)

        if stats.get("node_error", 0) > 0:
            WorkflowExecutor._write_retry_list(ctx, results, records)
            raise NodeError(f"检测到节点错误，已写入重算列表: {ctx.node_error_flag}")

        return stats

    @staticmethod
    def _run_olp_legacy(ctx: OLPContext, records: List[str]) -> List[Tuple[str, str]]:
        max_processes = ctx.max_processes
        with multiprocessing.Pool(processes=max_processes) as pool:
            execute_func = partial(OLPCommandExecutor.execute, ctx=ctx)
            results = pool.map(execute_func, records)
        return results

    @staticmethod
    def _run_olp_with_new_executor(
        ctx: OLPContext, records: List[str], logger: Any
    ) -> List[Tuple[str, str]]:
        executor = create_executor(
            "olp",
            config={
                "commands": ctx.config.get("commands", {}),
                "num_cores": ctx.num_cores,
                "max_processes": ctx.max_processes,
                "node_error_flag": ctx.node_error_flag,
            },
        )

        exec_ctx = WorkflowExecutor._create_olp_executor_context(ctx)
        results: List[Tuple[str, str]] = []

        for path in records:
            task = OlpTask(path=path)
            result = executor.run(task, exec_ctx)
            results.append((result.status.value, path))

        return results

    # ==================== Infer 阶段 ====================

    @staticmethod
    def run_infer_stage(
        global_config: str,
        group_index: int,
        path_resolver: Optional[PathResolver] = None,
        workdir: Optional[str] = None,
        batch_index: Optional[int] = None,
        use_new_executor: bool = False,
    ) -> Dict[str, Any]:
        """
        执行 Infer 阶段

        Args:
            global_config: 全局配置文件路径
            group_index: 组索引（1-based）
            path_resolver: 路径解析器（用于run/batch模式统一）
            workdir: 工作目录
            batch_index: batch索引（batch模式）
            use_new_executor: 使用新执行器架构（默认False，安全回滚）

        Returns:
            执行结果

        Raises:
            GroupNotFoundError: 组不存在
            TransformError: 格式转换失败
            InferError: 推理失败
        """
        logger = get_logger("executor.infer")
        logger.info("run_infer_stage: group_index=%d", group_index)

        config = load_global_config_section(Path(global_config), "1infer")

        if path_resolver is None:
            if batch_index is not None:
                workflow_root = Path(workdir) if workdir else Path.cwd()
                path_resolver = BatchPathResolver(workflow_root, batch_index)
            else:
                path_resolver = RunPathResolver(
                    Path(workdir) if workdir else Path.cwd()
                )

        workflow_root = path_resolver.get_workdir()
        result_dir = path_resolver.get_infer_output_dir()

        model_dir = Path(config.get("model_dir", ""))
        if not model_dir or not model_dir.exists():
            raise ValueError(f"model_dir does not exist or not configured: {model_dir}")

        ctx = InferContext(
            config=config,
            workflow_root=workflow_root,
            workdir=path_resolver.get_workdir(),
            result_dir=result_dir,
            error_file=path_resolver.get_infer_error_file(),
            hamlog_file=path_resolver.get_infer_hamlog_file(),
            group_info_file=workflow_root / "1infer" / GROUP_INFO_FILE,
            num_groups=config.get("num_groups", 10),
            random_seed=config.get("random_seed", 137),
            parallel=config.get("parallel", 56),
            model_dir=Path(config.get("model_dir", "/path/to/model")),
            dataset_prefix=config.get("dataset_prefix", "dataset"),
        )

        if use_new_executor:
            result = WorkflowExecutor._run_infer_with_new_executor(
                group_index, ctx, logger
            )
        else:
            try:
                result = InferCommandExecutor.execute(group_index, ctx)
                logger.info("run_infer_stage 完成: %s", result)
            except Exception as e:
                logger.error("run_infer_stage 失败: %s", e)
                raise

        return result

    @staticmethod
    def _run_infer_with_new_executor(
        group_index: int, ctx: InferContext, logger: Any
    ) -> Dict[str, Any]:
        executor = create_executor(
            "infer",
            config={
                "commands": ctx.config.get("commands", {}),
                "num_groups": ctx.num_groups,
                "parallel": ctx.parallel,
                "model_dir": str(ctx.model_dir),
            },
        )

        exec_ctx = WorkflowExecutor._create_infer_executor_context(ctx)

        task = InferTask(path="", scf_path="")
        result = executor.run(task, exec_ctx)

        if result.is_failed:
            logger.error("run_infer_stage 失败: %s", result.errors)
            raise RuntimeError(f"Infer failed: {result.errors}")

        logger.info("run_infer_stage 完成: group=%d", group_index)
        return {
            "group_index": group_index,
            "status": "success",
            "output": str(result.output_path),
        }

    # ==================== Calc 阶段 ====================

    @staticmethod
    def run_calc_stage(
        global_config: str,
        start: int,
        end: int,
        path_resolver: Optional[PathResolver] = None,
        workdir: Optional[str] = None,
        stru_log: Optional[str] = None,
        monitor: Optional[JobMonitor] = None,
        batch_index: Optional[int] = None,
        use_new_executor: bool = False,
    ) -> Dict[str, int]:
        """
        执行 Calc 阶段

        Args:
            global_config: 全局配置文件路径
            start: 起始索引
            end: 结束索引
            path_resolver: 路径解析器（用于run/batch模式统一）
            workdir: 工作目录
            stru_log: 结构列表文件（覆盖默认hamlog）
            monitor: 作业监控器
            batch_index: batch索引（batch模式）
            use_new_executor: 使用新执行器架构（默认False，安全回滚）

        Returns:
            {'success': N, 'failed': M}

        Raises:
            AbortException: 快速失败
        """
        logger = get_logger("executor.calc")
        logger.info("run_calc_stage: start=%d, end=%d", start, end)

        config = load_global_config_section(Path(global_config), "2calc")

        if path_resolver is None:
            if batch_index is not None:
                workflow_root = Path(workdir) if workdir else Path.cwd()
                path_resolver = BatchPathResolver(workflow_root, batch_index)
            else:
                path_resolver = RunPathResolver(
                    Path(workdir) if workdir else Path.cwd()
                )

        workflow_root = path_resolver.get_workdir()
        result_dir = path_resolver.get_calc_output_dir()

        ctx = CalcContext(
            config=config,
            workflow_root=workflow_root,
            workdir=path_resolver.get_workdir(),
            result_dir=result_dir,
            progress_file=path_resolver.get_calc_progress_file(),
            folders_file=path_resolver.get_calc_folders_file(),
            error_file=path_resolver.get_calc_error_file(),
            hamlog_file=path_resolver.get_infer_hamlog_file(),
            monitor=monitor,
        )

        records = WorkflowExecutor._read_calc_records(
            ctx, start, end, stru_log, path_resolver
        )
        logger.info("读取到 %d 条记录", len(records))

        if use_new_executor:
            results = WorkflowExecutor._run_calc_with_new_executor(ctx, records, logger)
        else:
            results = WorkflowExecutor._run_calc_legacy(ctx, records)

        if monitor:
            from .core.workflow_state import TaskError

            for status, label in results:
                if status in ["failed", "node_error"]:
                    ftype = (
                        FailureType.NODE_ERROR
                        if status == "node_error"
                        else FailureType.CALC_ERROR
                    )
                    monitor.report_error(
                        TaskError(
                            stage="2calc",
                            failure_type=ftype,
                            message=label,
                            timestamp=datetime.now(),
                        )
                    )

            if monitor.should_abort():
                raise AbortException(monitor.state.abort_reason or "Abort requested")

        stats = WorkflowExecutor._summarize_results(results)
        logger.info("run_calc_stage 完成: %s", stats)
        return stats

    @staticmethod
    def _run_calc_legacy(
        ctx: CalcContext, records: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        with multiprocessing.Pool(processes=1) as pool:
            execute_func = partial(CalcCommandExecutor.execute, ctx=ctx)
            results = pool.map(execute_func, records)
        return results

    @staticmethod
    def _run_calc_with_new_executor(
        ctx: CalcContext, records: List[Tuple[str, str]], logger: Any
    ) -> List[Tuple[str, str]]:
        executor = create_executor(
            "calc",
            config={
                "commands": ctx.config.get("commands", {}),
            },
        )

        exec_ctx = WorkflowExecutor._create_calc_executor_context(ctx)
        results: List[Tuple[str, str]] = []

        for path, geth_path in records:
            task = CalcTask(path=path, geth_path=geth_path)
            result = executor.run(task, exec_ctx)
            results.append((result.status.value, path))

        return results

    # ==================== 辅助函数 ====================

    @staticmethod
    def _read_olp_records(
        ctx: OLPContext,
        start: int,
        end: int,
        path_resolver: Optional[PathResolver] = None,
    ) -> List[str]:
        """读取OLP阶段记录

        支持两种模式:
        1. Batch模式: 从 olp_tasks.jsonl 读取
        2. Run模式: 从 stru_log 文件读取
        """
        if isinstance(path_resolver, BatchPathResolver):
            tasks_file = path_resolver.get_olp_tasks_file()
        else:
            stru_log = ctx.stru_log
            if stru_log is None:
                stru_log_path = ctx.config.get("stru_log")
                if stru_log_path:
                    stru_log = Path(stru_log_path)
                    if not stru_log.is_absolute():
                        stru_log = ctx.workflow_root / stru_log

            if stru_log is None:
                raise ValueError("未指定结构列表文件")
            tasks_file = stru_log

        with open(tasks_file, "r") as f:
            lines = f.readlines()

        records = []
        for i in range(start, min(end, len(lines))):
            data = json.loads(lines[i].strip())
            records.append(data["path"])

        return records

    @staticmethod
    def _read_calc_records(
        ctx: CalcContext,
        start: int,
        end: int,
        stru_log: Optional[str],
        path_resolver: Optional[PathResolver] = None,
    ) -> List[Tuple[str, str]]:
        """读取Calc阶段记录

        支持两种模式:
        1. Batch模式: 从 calc_tasks.jsonl 读取
        2. Run模式: 从 hamlog.dat 或 stru_log 读取

        支持两种格式：
        1. JSON Lines (calc_tasks.jsonl): {"path": "...", "geth_path": "..."}
        2. 纯文本 (hamlog.dat): label geth_path
        """
        if isinstance(path_resolver, BatchPathResolver):
            tasks_file = path_resolver.get_calc_tasks_file()
        elif stru_log:
            tasks_file = Path(stru_log)
        else:
            tasks_file = ctx.hamlog_file

        with open(tasks_file, "r") as f:
            lines = f.readlines()

        records = []
        for i in range(start, min(end, len(lines))):
            line = lines[i].strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                records.append((data["path"], data["geth_path"]))
            except json.JSONDecodeError:
                parts = line.split()
                if len(parts) >= 2:
                    records.append((parts[0], parts[1]))

        return records

    @staticmethod
    def _summarize_results(results: List[Tuple[str, str]]) -> Dict[str, int]:
        """统计结果"""
        stats = {}
        for status, _ in results:
            stats[status] = stats.get(status, 0) + 1
        return stats

    @staticmethod
    def _write_retry_list(
        ctx: OLPContext, results: List[Tuple[str, str]], records: List[str]
    ):
        """写入重算列表"""
        retry_labels = [
            Path(records[i]).name
            for i, (status, _) in enumerate(results)
            if status in ["node_error", "skipped"]
        ]

        if ctx.node_error_flag:
            with open(ctx.node_error_flag, "w") as f:
                for label in retry_labels:
                    f.write(f"{label}\n")
