#!/usr/bin/env python3
"""命令行入口 - argparse 实现"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def cmd_run(args):
    """运行工作流"""
    from .workflow import WorkflowManager

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.run(daemon=args.daemon)


def cmd_status(args):
    """查看状态"""
    from .workflow import WorkflowManager

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.show_status()


def cmd_stop(args):
    """停止运行"""
    from .workflow import WorkflowManager

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.stop()


def cmd_restart(args):
    """重新开始"""
    from .workflow import WorkflowManager

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.restart(daemon=args.daemon)


def cmd_olp(args):
    """执行 OLP 阶段"""
    from .executor import WorkflowExecutor

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    result = WorkflowExecutor.run_olp_stage(
        global_config=str(config_path),
        start=args.start,
        end=args.end,
        workdir=str(workdir),
    )
    print(f"OLP 完成: {result}")


def cmd_infer(args):
    """执行 Infer 阶段"""
    from .executor import WorkflowExecutor

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    result = WorkflowExecutor.run_infer_stage(
        global_config=str(config_path),
        group_index=args.group,
        workdir=str(workdir),
    )
    print(f"Infer 完成: {result}")


def cmd_calc(args):
    """执行 Calc 阶段"""
    from .executor import WorkflowExecutor

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    result = WorkflowExecutor.run_calc_stage(
        global_config=str(config_path),
        start=args.start,
        end=args.end,
        workdir=str(workdir),
    )
    print(f"Calc 完成: {result}")


def cmd_validate(args):
    """验证配置文件"""
    from .utils import load_yaml_config

    config_path = Path(args.config).resolve()

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    try:
        config = load_yaml_config(config_path)

        required_sections = ["software", "0olp", "1infer", "2calc"]
        missing = [s for s in required_sections if s not in config]

        if missing:
            print(f"错误: 配置文件缺少以下部分: {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)

        print(f"配置文件验证通过: {config_path}")
        print(f"  - 包含 {len(config)} 个配置段")
        print(f"  - 软件路径: {len(config.get('software', {}))} 项")

    except Exception as e:
        print(f"错误: 配置文件解析失败: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_version(args):
    """显示版本"""
    print(f"dlazy {__version__}")


def cmd_batch(args):
    """运行批量工作流"""
    from .batch_workflow import BatchScheduler
    from .contexts import BatchContext

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    if not config_path.exists():
        print(f"错误: 配置文件不存在: {config_path}", file=sys.stderr)
        sys.exit(1)

    ctx = BatchContext(
        config_path=config_path,
        workflow_root=workdir,
        batch_size=args.batch_size,
        fresh=args.fresh,
    )

    scheduler = BatchScheduler(ctx)
    result = scheduler.run()
    print(f"批量工作流完成: {result}")


def cmd_batch_status(args):
    """查看批量工作流状态 - 只读模式，不修改状态文件"""
    import json
    import os

    from .constants import (
        BATCH_STATE_FILE,
        BATCH_PID_FILE,
        BATCH_STAGES,
        MONITOR_STATE_FILE,
        BATCH_DIR_PREFIX,
        TASK_DIR_PREFIX,
        PROGRESS_FILE,
    )

    def count_lines(file_path):
        if not file_path.exists():
            return 0
        with open(file_path, "r") as f:
            return sum(1 for _ in f)

    def count_progress_ends(progress_file):
        """统计 progress 文件中的 end 行数"""
        if not progress_file.exists():
            return 0
        count = 0
        with open(progress_file, "r") as f:
            for line in f:
                if line.strip().endswith(" end"):
                    count += 1
        return count

    def count_dirs(dir_path, prefix="task."):
        if not dir_path.exists():
            return 0
        return len(
            [d for d in dir_path.iterdir() if d.is_dir() and d.name.startswith(prefix)]
        )

    def count_infer_outputs(infer_dir):
        """统计 infer 实际完成的任务数（geth/task.XXX 目录数）"""
        if not infer_dir.exists():
            return 0
        count = 0
        for group_dir in infer_dir.iterdir():
            if group_dir.is_dir() and group_dir.name.startswith("g."):
                geth_dir = group_dir / "geth"
                if geth_dir.exists():
                    count += count_dirs(geth_dir, "task.")
        return count

    def count_calc_outputs(calc_dir):
        """统计 calc 实际完成的任务数"""
        if not calc_dir.exists():
            return 0
        return count_dirs(calc_dir, "task.")

    def progress_bar(completed, total, width=20):
        if total == 0:
            return "░" * width
        pct = completed / total
        filled = int(width * pct)
        return "█" * filled + "░" * (width - filled)

    def get_batch_progress(workdir, batch_index):
        batch_dir = workdir / f"{BATCH_DIR_PREFIX}.{batch_index:05d}"

        olp_total = count_lines(batch_dir / "slurm_olp" / "olp_tasks.jsonl")
        olp_done = count_progress_ends(batch_dir / "slurm_olp" / PROGRESS_FILE)

        infer_total = olp_done
        infer_done = count_progress_ends(batch_dir / "slurm_infer" / PROGRESS_FILE)

        calc_total = infer_done
        calc_done = count_progress_ends(batch_dir / "slurm_calc" / PROGRESS_FILE)

        error_done = count_lines(batch_dir / "error_tasks.jsonl")

        return {
            "olp": {"total": olp_total, "done": olp_done},
            "infer": {"total": infer_total, "done": infer_done},
            "calc": {"total": calc_total, "done": calc_done},
            "error": error_done,
        }

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    print("=== 批量工作流状态 ===")

    pid_file = workdir / BATCH_PID_FILE
    if not pid_file.exists():
        print("进程状态: 未运行\n")
        running = False
    else:
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            print(f"进程状态: 运行中 (PID: {pid})\n")
            running = True
        except (ValueError, OSError):
            print("进程状态: 已停止\n")
            running = False

    state_file = workdir / BATCH_STATE_FILE
    if not state_file.exists():
        print("批量工作流未启动或状态文件不存在")
        return

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    total_batches = state.get("total_batches", 0)
    completed_batches = len(state.get("completed_batches", []))
    current_batch = state.get("current_batch", 0)
    current_stage = state.get("current_stage", "olp")
    initialized = state.get("initialized", False)

    if not initialized:
        print("状态: 未初始化")
        return

    total_tasks = 0
    total_olp_done = 0
    total_infer_done = 0
    total_calc_done = 0
    total_errors = 0

    for batch_idx in range(total_batches):
        progress = get_batch_progress(workdir, batch_idx)
        total_tasks += progress["olp"]["total"]
        total_olp_done += progress["olp"]["done"]
        total_infer_done += progress["infer"]["done"]
        total_calc_done += progress["calc"]["done"]
        total_errors += progress["error"]

    print(f"总任务数: {total_tasks} | 批次: {completed_batches}/{total_batches} 完成")
    print()
    print("┌" + "─" * 50 + "┐")
    print("│ 阶段  │ 完成/总数   │ 进度                      │")
    print("├" + "─" * 50 + "┤")
    print(
        f"│ olp   │ {total_olp_done:4d}/{total_tasks:4d}    │ {progress_bar(total_olp_done, total_tasks)} {100 * total_olp_done / max(total_tasks, 1):5.1f}% │"
    )
    print(
        f"│ infer │ {total_infer_done:4d}/{total_tasks:4d}    │ {progress_bar(total_infer_done, total_tasks)} {100 * total_infer_done / max(total_tasks, 1):5.1f}% │"
    )
    print(
        f"│ calc  │ {total_calc_done:4d}/{total_tasks:4d}    │ {progress_bar(total_calc_done, total_tasks)} {100 * total_calc_done / max(total_tasks, 1):5.1f}% │"
    )
    print("└" + "─" * 50 + "┘")

    if total_errors > 0:
        print(f"\n⚠ 错误任务: {total_errors} 个")

    if current_batch < total_batches:
        print(f"\n当前批次: batch.{current_batch:05d} ({current_stage} 阶段)")
        progress = get_batch_progress(workdir, current_batch)
        batch_total = progress["olp"]["total"]
        if batch_total > 0:
            print(f"  OLP:   {progress['olp']['done']:3d}/{batch_total:3d}")
            print(f"  Infer: {progress['infer']['done']:3d}/{batch_total:3d}")
            print(f"  Calc:  {progress['calc']['done']:3d}/{batch_total:3d}")

    if state.get("current_job_id"):
        print(f"\n当前作业: {state.get('current_job_id')}")

    if state.get("last_update"):
        print(f"最后更新: {state.get('last_update')}")

    monitor_file = workdir / MONITOR_STATE_FILE
    if monitor_file.exists():
        with open(monitor_file, "r", encoding="utf-8") as f:
            monitor_state = json.load(f)

        errors = monitor_state.get("errors", [])
        if errors:
            print(f"\n错误记录: {len(errors)} 条 (最近 3 条)")
            for err in errors[-3:]:
                print(
                    f"  - [{err.get('stage')}] {err.get('failure_type')}: {err.get('message')}"
                )

        if monitor_state.get("abort_flag"):
            print(f"\n⛔ 中断原因: {monitor_state.get('abort_reason', '未知')}")


def cmd_batch_stop(args):
    """停止批量工作流"""
    from .batch_workflow import BatchScheduler
    from .contexts import BatchContext

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    ctx = BatchContext(
        config_path=config_path,
        workflow_root=workdir,
        batch_size=100,
    )

    scheduler = BatchScheduler(ctx)
    scheduler.stop()


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="dlazy",
        description="Material calculation workflow automation system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    parser.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    parser_run = subparsers.add_parser("run", help="运行工作流")
    parser_run.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_run.add_argument("--workdir", help="工作目录 (默认为配置文件所在目录)")
    parser_run.add_argument("--daemon", action="store_true", help="后台运行")
    parser_run.set_defaults(func=cmd_run)

    parser_status = subparsers.add_parser("status", help="查看工作流状态")
    parser_status.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_status.add_argument("--workdir", help="工作目录")
    parser_status.set_defaults(func=cmd_status)

    parser_stop = subparsers.add_parser("stop", help="停止工作流")
    parser_stop.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_stop.add_argument("--workdir", help="工作目录")
    parser_stop.set_defaults(func=cmd_stop)

    parser_restart = subparsers.add_parser("restart", help="重新开始工作流")
    parser_restart.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_restart.add_argument("--workdir", help="工作目录")
    parser_restart.add_argument("--daemon", action="store_true", help="后台运行")
    parser_restart.set_defaults(func=cmd_restart)

    parser_olp = subparsers.add_parser("olp", help="执行 OLP 阶段")
    parser_olp.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_olp.add_argument("--workdir", help="工作目录")
    parser_olp.add_argument("--start", type=int, default=0, help="起始索引")
    parser_olp.add_argument("--end", type=int, default=10, help="结束索引")
    parser_olp.set_defaults(func=cmd_olp)

    parser_infer = subparsers.add_parser("infer", help="执行 Infer 阶段")
    parser_infer.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_infer.add_argument("--workdir", help="工作目录")
    parser_infer.add_argument(
        "--group", type=int, required=True, help="组索引 (1-based)"
    )
    parser_infer.set_defaults(func=cmd_infer)

    parser_calc = subparsers.add_parser("calc", help="执行 Calc 阶段")
    parser_calc.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_calc.add_argument("--workdir", help="工作目录")
    parser_calc.add_argument("--start", type=int, default=0, help="起始索引")
    parser_calc.add_argument("--end", type=int, default=10, help="结束索引")
    parser_calc.set_defaults(func=cmd_calc)

    parser_validate = subparsers.add_parser("validate", help="验证配置文件")
    parser_validate.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_validate.set_defaults(func=cmd_validate)

    parser_version = subparsers.add_parser("version", help="显示版本")
    parser_version.set_defaults(func=cmd_version)

    parser_batch = subparsers.add_parser("batch", help="运行批量工作流")
    parser_batch.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_batch.add_argument("--workdir", help="工作目录 (默认为配置文件所在目录)")
    parser_batch.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="每批次任务数量 (默认: 100)",
    )
    parser_batch.add_argument(
        "--fresh",
        action="store_true",
        help="从头开始（删除已有状态）",
    )
    parser_batch.set_defaults(func=cmd_batch)

    parser_batch_status = subparsers.add_parser(
        "batch-status", help="查看批量工作流状态"
    )
    parser_batch_status.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_batch_status.add_argument("--workdir", help="工作目录")
    parser_batch_status.set_defaults(func=cmd_batch_status)

    parser_batch_stop = subparsers.add_parser("batch-stop", help="停止批量工作流")
    parser_batch_stop.add_argument(
        "--config",
        default="global_config.yaml",
        help="配置文件路径 (默认: ./global_config.yaml)",
    )
    parser_batch_stop.add_argument("--workdir", help="工作目录")
    parser_batch_stop.set_defaults(func=cmd_batch_stop)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
