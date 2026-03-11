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
    from .batch_workflow import BatchWorkflowManager
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
        resume=args.resume,
    )

    manager = BatchWorkflowManager(ctx)
    result = manager.run()
    print(f"批量工作流完成: {result}")


def cmd_batch_status(args):
    """查看批量工作流状态"""
    import json
    from .constants import BATCH_STATE_FILE

    config_path = Path(args.config).resolve()
    workdir = Path(args.workdir).resolve() if args.workdir else config_path.parent

    state_file = workdir / BATCH_STATE_FILE
    if not state_file.exists():
        print("批量工作流未启动或状态文件不存在")
        return

    with open(state_file, "r", encoding="utf-8") as f:
        state = json.load(f)

    print("批量工作流状态:")
    print(f"  当前批次: {state.get('current_batch', 0)}")
    print(f"  当前阶段: {state.get('current_stage', 'N/A')}")
    print(f"  已完成批次: {len(state.get('completed_batches', []))}")
    print(f"  OLP完成: {state.get('olp_completed', False)}")
    print(f"  Infer完成: {state.get('infer_completed', False)}")
    print(f"  Calc完成: {state.get('calc_completed', False)}")


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
        "--resume",
        action="store_true",
        help="从上次中断处继续",
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

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
