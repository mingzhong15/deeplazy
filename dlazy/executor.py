"""工作流执行器 - 统一入口"""

from __future__ import annotations

import json
import multiprocessing
import secrets
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
from .exceptions import AbortException, FailureType, NodeError
from .utils import (
    get_logger,
    get_result_geth_dir,
    get_result_infer_dir,
    get_result_olp_dir,
    get_workflow_root,
    load_global_config_section,
)

if TYPE_CHECKING:
    from .monitor import JobMonitor, TaskError


class WorkflowExecutor:
    """工作流执行器 - 封装三阶段逻辑"""

    # ==================== OLP 阶段 ====================

    @staticmethod
    def run_olp_stage(
        global_config: str,
        start: int,
        end: int,
        workdir: Optional[str] = None,
        stru_log: Optional[str] = None,
        monitor: Optional[JobMonitor] = None,
    ) -> Dict[str, int]:
        """
        执行 OLP 阶段

        Args:
            global_config: 全局配置文件路径
            start: 起始索引
            end: 结束索引
            workdir: 工作目录（默认当前目录）
            stru_log: 结构列表文件（覆盖配置）
            monitor: 作业监控器

        Returns:
            {'success': N, 'failed': M, 'skipped': K}

        Raises:
            ConfigError: 配置错误
            NodeError: 节点错误（需要重算）
            AbortException: 快速失败
        """
        logger = get_logger("executor.olp")
        logger.info("run_olp_stage: start=%d, end=%d, workdir=%s", start, end, workdir)

        config = load_global_config_section(Path(global_config), "0olp")
        workdir = Path(workdir) if workdir else Path.cwd()

        workflow_root = get_workflow_root(workdir)
        result_dir = get_result_olp_dir(workflow_root)

        ctx = OLPContext(
            config=config,
            workflow_root=workflow_root,
            workdir=workdir,
            result_dir=result_dir,
            progress_file=workdir / PROGRESS_FILE,
            folders_file=workdir / FOLDERS_FILE,
            error_file=workdir / ERROR_FILE,
            num_cores=config.get("num_cores", 56),
            max_processes=config.get("max_processes", 7),
            node_error_flag=workdir / f".node_error_flag-{secrets.token_hex(4)}",
            stru_log=Path(stru_log) if stru_log else None,
            monitor=monitor,
        )

        records = WorkflowExecutor._read_olp_records(ctx, start, end)
        logger.info("读取到 %d 条记录", len(records))

        max_processes = ctx.max_processes
        with multiprocessing.Pool(processes=max_processes) as pool:
            execute_func = partial(OLPCommandExecutor.execute, ctx=ctx)
            results = pool.map(execute_func, records)

        if monitor:
            from .monitor import TaskError

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
                raise AbortException(monitor.state.abort_reason)

        stats = WorkflowExecutor._summarize_results(results)
        logger.info("run_olp_stage 完成: %s", stats)

        if stats.get("node_error", 0) > 0:
            WorkflowExecutor._write_retry_list(ctx, results, records)
            raise NodeError(f"检测到节点错误，已写入重算列表: {ctx.node_error_flag}")

        return stats

    # ==================== Infer 阶段 ====================

    @staticmethod
    def run_infer_stage(
        global_config: str, group_index: int, workdir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行 Infer 阶段

        Args:
            global_config: 全局配置文件路径
            group_index: 组索引（1-based）
            workdir: 工作目录

        Returns:
            执行结果

        Raises:
            GroupNotFoundError: 组不存在
            TransformError: 格式转换失败
            InferError: 推理失败
        """
        logger = get_logger("executor.infer")
        logger.info("run_infer_stage: group_index=%d, workdir=%s", group_index, workdir)

        # 1. 加载配置
        config = load_global_config_section(Path(global_config), "1infer")
        workdir = Path(workdir) if workdir else Path.cwd()

        # 2. 创建上下文
        workflow_root = get_workflow_root(workdir)
        result_dir = get_result_infer_dir(workflow_root)

        ctx = InferContext(
            config=config,
            workflow_root=workflow_root,
            workdir=workdir,
            result_dir=result_dir,
            error_file=workdir / ERROR_FILE,
            hamlog_file=workdir / HAMLOG_FILE,
            group_info_file=workdir / GROUP_INFO_FILE,
            num_groups=config.get("num_groups", 10),
            random_seed=config.get("random_seed", 137),
            parallel=config.get("parallel", 56),
            model_dir=Path(config.get("model_dir", "/path/to/model")),
            dataset_prefix=config.get("dataset_prefix", "dataset"),
        )

        # 3. 执行推理
        try:
            result = InferCommandExecutor.execute(group_index, ctx)
            logger.info("run_infer_stage 完成: %s", result)
            return result
        except Exception as e:
            logger.error("run_infer_stage 失败: %s", e)
            raise

    # ==================== Calc 阶段 ====================

    @staticmethod
    def run_calc_stage(
        global_config: str,
        start: int,
        end: int,
        workdir: Optional[str] = None,
        stru_log: Optional[str] = None,
        monitor: Optional[JobMonitor] = None,
    ) -> Dict[str, int]:
        """
        执行 Calc 阶段

        Args:
            global_config: 全局配置文件路径
            start: 起始索引
            end: 结束索引
            workdir: 工作目录
            stru_log: 结构列表文件（覆盖默认hamlog）
            monitor: 作业监控器

        Returns:
            {'success': N, 'failed': M}

        Raises:
            AbortException: 快速失败
        """
        logger = get_logger("executor.calc")
        logger.info("run_calc_stage: start=%d, end=%d, workdir=%s", start, end, workdir)

        config = load_global_config_section(Path(global_config), "2calc")
        workdir = Path(workdir) if workdir else Path.cwd()

        workflow_root = get_workflow_root(workdir)
        result_dir = get_result_geth_dir(workflow_root)

        ctx = CalcContext(
            config=config,
            workflow_root=workflow_root,
            workdir=workdir,
            result_dir=result_dir,
            progress_file=workdir / PROGRESS_FILE,
            folders_file=workdir / FOLDERS_FILE,
            error_file=workdir / ERROR_FILE,
            hamlog_file=workflow_root / "1infer" / HAMLOG_FILE,
            monitor=monitor,
        )

        records = WorkflowExecutor._read_calc_records(ctx, start, end, stru_log)
        logger.info("读取到 %d 条记录", len(records))

        with multiprocessing.Pool(processes=1) as pool:
            execute_func = partial(CalcCommandExecutor.execute, ctx=ctx)
            results = pool.map(execute_func, records)

        if monitor:
            from .monitor import TaskError

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
                raise AbortException(monitor.state.abort_reason)

        stats = WorkflowExecutor._summarize_results(results)
        logger.info("run_calc_stage 完成: %s", stats)
        return stats

    # ==================== 辅助函数 ====================

    @staticmethod
    def _read_olp_records(ctx: OLPContext, start: int, end: int) -> List[str]:
        """读取OLP阶段记录"""
        stru_log = ctx.stru_log
        if stru_log is None:
            stru_log_path = ctx.config.get("stru_log")
            if stru_log_path:
                stru_log = Path(stru_log_path)
                if not stru_log.is_absolute():
                    stru_log = ctx.workflow_root / stru_log

        if stru_log is None:
            raise ValueError("未指定结构列表文件")

        with open(stru_log, "r") as f:
            lines = f.readlines()

        records = []
        for i in range(start, min(end, len(lines))):
            data = json.loads(lines[i].strip())
            records.append(data["path"])

        return records

    @staticmethod
    def _read_calc_records(
        ctx: CalcContext, start: int, end: int, stru_log: Optional[str]
    ) -> List[Tuple[str, str]]:
        """读取Calc阶段记录"""
        hamlog = Path(stru_log) if stru_log else ctx.hamlog_file

        with open(hamlog, "r") as f:
            lines = f.readlines()

        records = []
        for i in range(start, min(end, len(lines))):
            parts = lines[i].strip().split()
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
