#!/usr/bin/env python3
"""命令行入口 - argparse 实现"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel

from . import __version__
from .utils.security import validate_path
from .utils import get_existing_batch_count, get_next_backup_index

console = Console()


def cmd_run(args):
    """运行工作流"""
    from .workflow import WorkflowManager

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.run(daemon=args.daemon)


def cmd_status(args):
    """查看状态"""
    from .workflow import WorkflowManager

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.show_status()


def cmd_stop(args):
    """停止运行"""
    from .workflow import WorkflowManager

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.stop()


def cmd_restart(args):
    """重新开始"""
    from .workflow import WorkflowManager

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    manager = WorkflowManager(config_path=config_path, workdir=workdir)
    manager.restart(daemon=args.daemon)


def cmd_olp(args):
    """执行 OLP 阶段"""
    from .executor import WorkflowExecutor

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    if args.start < 0:
        print("错误: --start 不能为负数", file=sys.stderr)
        sys.exit(1)
    if args.end <= args.start:
        print("错误: --end 必须大于 --start", file=sys.stderr)
        sys.exit(1)

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

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    if args.group < 1:
        print("错误: --group 必须为正整数", file=sys.stderr)
        sys.exit(1)

    result = WorkflowExecutor.run_infer_stage(
        global_config=str(config_path),
        group_index=args.group,
        workdir=str(workdir),
    )
    print(f"Infer 完成: {result}")


def cmd_calc(args):
    """执行 Calc 阶段"""
    from .executor import WorkflowExecutor

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    if args.start < 0:
        print("错误: --start 不能为负数", file=sys.stderr)
        sys.exit(1)
    if args.end <= args.start:
        print("错误: --end 必须大于 --start", file=sys.stderr)
        sys.exit(1)

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

    config_path = validate_path(args.config, must_exist=True)

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
    import shutil
    from .batch_workflow import BatchScheduler
    from .contexts import BatchContext
    from .utils import get_existing_batch_count

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    # 检查已有batch目录，决定处理方式
    existing_count = get_existing_batch_count(workdir)
    batch_mode = args.batch_mode

    if existing_count > 0 and batch_mode == "auto":
        print(f"\n检测到已有批次: batch.00000 ~ batch.{existing_count - 1:05d}")
        print("请选择处理方式:")
        print("  [1] append    - 从 batch.{:05d} 继续添加新批次".format(existing_count))
        print("  [2] overwrite - 删除所有批次，从 batch.00000 重新开始")

        while True:
            choice = input("请输入选择 (1/2): ").strip()
            if choice == "1":
                batch_mode = "append"
                break
            elif choice == "2":
                batch_mode = "overwrite"
                break
            else:
                print("无效输入，请输入 1 或 2")

    if batch_mode == "overwrite" and existing_count > 0:
        print(f"正在删除 {existing_count} 个已有批次...")
        for i in range(existing_count):
            batch_dir = workdir / f"batch.{i:05d}"
            if batch_dir.exists():
                shutil.rmtree(batch_dir)
        # 同时清理状态文件
        state_file = workdir / "batch_state.json"
        if state_file.exists():
            state_file.unlink()
        monitor_file = workdir / "monitor_state.json"
        if monitor_file.exists():
            monitor_file.unlink()
        print("已清理所有批次和状态文件")

    ctx = BatchContext(
        config_path=config_path,
        workflow_root=workdir,
        batch_size=args.batch_size,
        fresh=(batch_mode == "overwrite"),
    )

    scheduler = BatchScheduler(ctx)
    result = scheduler.run()
    print(f"批量工作流完成: {result}")


def cmd_batch_status(args):
    """查看批量工作流状态 - 只读模式，不修改状态文件"""
    import json
    import math
    import os

    from .constants import (
        BATCH_STATE_FILE,
        BATCH_PID_FILE,
        BATCH_STAGES,
        MONITOR_STATE_FILE,
        BATCH_DIR_PREFIX,
        TASK_DIR_PREFIX,
        PROGRESS_FILE,
        SLURM_SUBDIR_TEMPLATE,
        ERROR_TASKS_FILE,
        PERMANENT_ERRORS_FILE,
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

    def count_total_errors(workdir, batch_index):
        """统计所有阶段的错误任务数"""
        batch_dir = workdir / f"{BATCH_DIR_PREFIX}.{batch_index:05d}"
        total = 0
        for stage in BATCH_STAGES:
            error_file = (
                batch_dir / SLURM_SUBDIR_TEMPLATE.format(stage) / ERROR_TASKS_FILE
            )
            total += count_lines(error_file)
        return total

    def get_total_tasks_from_todo(workdir):
        """从 todo_list.json 获取原始总任务数"""
        todo_file = workdir / "todo_list.json"
        return count_lines(todo_file)

    def get_original_task_count(workdir, state):
        """从状态文件或 todo_list.origin 获取原始任务数"""
        if state.get("original_task_count"):
            return state["original_task_count"]

        origin_file = workdir / "todo_list.origin"
        if origin_file.exists():
            return count_lines(origin_file)

        return count_lines(workdir / "todo_list.json")

    def count_progress_errors(progress_file):
        """统计 progress 文件中的 error 行数"""
        if not progress_file.exists():
            return 0
        count = 0
        with open(progress_file, "r") as f:
            for line in f:
                if line.strip().endswith(" error"):
                    count += 1
        return count

    def get_batch_detailed_status(workdir, batch_index, completed_batches, batch_times):
        """获取单个批次的详细状态"""
        from datetime import datetime

        batch_dir = workdir / f"{BATCH_DIR_PREFIX}.{batch_index:05d}"

        if not batch_dir.exists():
            return {
                "total": 0,
                "olp_done": 0,
                "infer_done": 0,
                "calc_done": 0,
                "errors": 0,
                "status": "pending",
                "start_time": None,
                "end_time": None,
            }

        olp_total = count_lines(batch_dir / "slurm_olp" / "olp_tasks.jsonl")
        olp_done = count_progress_ends(batch_dir / "slurm_olp" / PROGRESS_FILE)
        infer_done = count_progress_ends(batch_dir / "slurm_infer" / PROGRESS_FILE)
        calc_done = count_progress_ends(batch_dir / "slurm_calc" / PROGRESS_FILE)
        errors = count_total_errors(workdir, batch_index)

        if batch_index in completed_batches:
            status = "completed"
        elif olp_total > 0:
            status = "running"
        else:
            status = "pending"

        time_info = batch_times.get(str(batch_index), {})

        return {
            "total": olp_total,
            "olp_done": olp_done,
            "infer_done": infer_done,
            "calc_done": calc_done,
            "errors": errors,
            "status": status,
            "start_time": time_info.get("start"),
            "end_time": time_info.get("end"),
        }

    def format_time_display(start_time, end_time, status):
        """格式化时间显示: MM-DD HH:MM-HH:MM"""
        from datetime import datetime

        if status == "pending":
            return "-"

        start_str = ""
        end_str = "-"

        if start_time:
            try:
                dt = datetime.fromisoformat(start_time)
                start_str = dt.strftime("%m-%d %H:%M")
            except:
                start_str = "-"

        if end_time:
            try:
                dt = datetime.fromisoformat(end_time)
                end_str = dt.strftime("%H:%M")
            except:
                end_str = "-"

        return f"{start_str}-{end_str}"

    def get_permanent_errors(workdir):
        """获取永久失败任务列表"""
        perm_file = workdir / PERMANENT_ERRORS_FILE
        if not perm_file.exists():
            return []
        errors = []
        with open(perm_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        import json

                        data = json.loads(line)
                        errors.append(data.get("path", "unknown"))
                    except:
                        pass
        return errors

    def progress_bar(completed, total, width=30):
        if total == 0:
            return "░" * width
        pct = completed / total
        filled = int(width * pct)
        return "█" * filled + "░" * (width - filled)

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

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

    total_original_tasks = get_original_task_count(workdir, state)
    batch_times = state.get("batch_times", {})
    completed_batch_indices = set(state.get("completed_batches", []))

    batch_statuses = []
    total_processed = 0
    total_relay_tasks = 0
    total_olp_done = 0
    total_infer_done = 0
    total_calc_done = 0
    total_errors = 0
    total_olp_errors = 0
    total_infer_errors = 0
    total_calc_errors = 0

    for batch_idx in range(total_batches):
        batch_status = get_batch_detailed_status(
            workdir, batch_idx, completed_batch_indices, batch_times
        )
        batch_statuses.append(batch_status)
        total_processed += batch_status["total"]
        total_olp_done += batch_status["olp_done"]
        total_infer_done += batch_status["infer_done"]
        total_calc_done += batch_status["calc_done"]
        total_errors += batch_status["errors"]

        batch_dir = workdir / f"{BATCH_DIR_PREFIX}.{batch_idx:05d}"
        total_olp_errors += count_progress_errors(
            batch_dir / "slurm_olp" / PROGRESS_FILE
        )
        total_infer_errors += count_progress_errors(
            batch_dir / "slurm_infer" / PROGRESS_FILE
        )
        total_calc_errors += count_progress_errors(
            batch_dir / "slurm_calc" / PROGRESS_FILE
        )

    total_relay_tasks = total_processed - total_original_tasks

    batch_size = (
        math.ceil(total_original_tasks / total_batches) if total_batches > 0 else 0
    )

    def get_batch_original_count(batch_idx, total_original, batch_sz, total_b):
        if batch_sz == 0 or total_original == 0:
            return 0
        start = batch_idx * batch_sz
        if start >= total_original:
            return 0
        return min(batch_sz, total_original - start)

    permanent_errors = get_permanent_errors(workdir)
    total_permanent_errors = len(permanent_errors)
    retrying_tasks = total_errors - total_permanent_errors
    success_tasks = total_calc_done

    console.print()
    console.rule("[bold blue]总体进度", style="blue")
    console.print(f"原始任务: [cyan]{total_original_tasks}[/cyan]")
    relay_str = f"处理次数: [cyan]{total_processed}[/cyan] (原始 {total_original_tasks}"
    if total_relay_tasks > 0:
        relay_str += f" + 中继 [yellow]{total_relay_tasks}[/yellow])"
    else:
        relay_str += ")"
    console.print(relay_str)
    if total_processed > 0:
        console.print(
            f"成功: [green]{success_tasks}[/green] | 重试中: [yellow]{retrying_tasks}[/yellow] | 永久失败: [red]{total_permanent_errors}[/red]"
        )
    console.print()

    stage_table = Table(title="阶段进度", show_header=True, header_style="bold magenta")
    stage_table.add_column("阶段", style="cyan", width=8)
    stage_table.add_column("完成", justify="right", width=8)
    stage_table.add_column("成功", justify="right", width=8)
    stage_table.add_column("失败", justify="right", width=8)
    stage_table.add_column("进度", width=30)

    olp_success = (
        total_olp_done - total_olp_errors
        if total_olp_done >= total_olp_errors
        else total_olp_done
    )
    infer_success = (
        total_infer_done - total_infer_errors
        if total_infer_done >= total_infer_errors
        else total_infer_done
    )
    calc_success = (
        total_calc_done - total_calc_errors
        if total_calc_done >= total_calc_errors
        else total_calc_done
    )

    total_for_progress = (
        total_original_tasks if total_original_tasks > 0 else total_processed
    )

    def rich_progress_bar(done, total, width=20):
        if total == 0:
            return "[dim]━━━━━━━━━━━━━━━━━━━━[/dim] 0%"
        pct = done / total
        filled = int(width * pct)
        bar = "█" * filled + "░" * (width - filled)
        return f"[green]{bar}[/green] {pct * 100:.1f}%"

    stage_table.add_row(
        "OLP",
        str(total_olp_done),
        f"[green]{olp_success}[/green]",
        f"[red]{total_olp_errors}[/red]"
        if total_olp_errors > 0
        else str(total_olp_errors),
        rich_progress_bar(total_olp_done, total_for_progress),
    )
    stage_table.add_row(
        "Infer",
        str(total_infer_done),
        f"[green]{infer_success}[/green]",
        f"[red]{total_infer_errors}[/red]"
        if total_infer_errors > 0
        else str(total_infer_errors),
        rich_progress_bar(total_infer_done, total_for_progress),
    )
    stage_table.add_row(
        "Calc",
        str(total_calc_done),
        f"[green]{calc_success}[/green]",
        f"[red]{total_calc_errors}[/red]"
        if total_calc_errors > 0
        else str(total_calc_errors),
        rich_progress_bar(total_calc_done, total_for_progress),
    )
    console.print(stage_table)

    console.print()
    console.rule("[bold blue]各批次详情", style="blue")

    batch_table = Table(show_header=True, header_style="bold magenta")
    batch_table.add_column("批次", style="cyan", width=14)
    batch_table.add_column("任务(原+中继)", justify="right", width=14)
    batch_table.add_column("OLP", justify="right", width=6)
    batch_table.add_column("Infer", justify="right", width=6)
    batch_table.add_column("Calc", justify="right", width=6)
    batch_table.add_column("状态", width=10)

    for batch_idx, batch_status in enumerate(batch_statuses):
        batch_name = f"batch.{batch_idx:05d}"
        total = batch_status["total"]
        olp = batch_status["olp_done"]
        infer = batch_status["infer_done"]
        calc = batch_status["calc_done"]
        errors = batch_status["errors"]
        status = batch_status["status"]

        batch_original = get_batch_original_count(
            batch_idx, total_original_tasks, batch_size, total_batches
        )
        batch_relay = total - batch_original
        if batch_relay < 0:
            batch_relay = 0

        if status == "completed":
            if errors > 0:
                status_display = "[yellow]有错误[/yellow]"
            else:
                status_display = "[green]完成[/green]"
        elif status == "running":
            status_display = "[blue]进行中[/blue]"
        else:
            status_display = "[dim]待处理[/dim]"

        task_str = (
            f"{total} ([cyan]{batch_original}[/cyan]+[yellow]{batch_relay}[/yellow])"
            if batch_relay > 0
            else str(total)
        )

        batch_table.add_row(
            batch_name,
            task_str,
            str(olp),
            str(infer),
            str(calc),
            status_display,
        )
    console.print(batch_table)

    console.print()
    current_job_id = state.get("current_job_id")
    if current_job_id:
        console.print(
            f"当前作业: [cyan]{current_job_id}[/cyan] | 阶段: [yellow]{current_stage}[/yellow] | 最后更新: {state.get('last_update', '-')}"
        )
    elif state.get("last_update"):
        console.print(f"最后更新: {state.get('last_update')}")

    if total_permanent_errors > 0:
        console.print()
        console.print(
            Panel(f"[red]永久失败任务 ({total_permanent_errors})[/red]", title="警告")
        )

    monitor_file = workdir / MONITOR_STATE_FILE
    if monitor_file.exists():
        with open(monitor_file, "r", encoding="utf-8") as f:
            monitor_state = json.load(f)

        errors_list = monitor_state.get("errors", [])
        if errors_list:
            print()
            print(f"错误记录: {len(errors_list)} 条 (最近 3 条)")
            for err in errors_list[-3:]:
                print(
                    f"  - [{err.get('stage')}] {err.get('failure_type')}: {err.get('message')}"
                )

        if monitor_state.get("abort_flag"):
            print()
            print(f"⛔ 中断原因: {monitor_state.get('abort_reason', '未知')}")


def cmd_batch_stop(args):
    """停止批量工作流"""
    from .batch_workflow import BatchScheduler
    from .contexts import BatchContext

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    ctx = BatchContext(
        config_path=config_path,
        workflow_root=workdir,
        batch_size=100,
    )

    scheduler = BatchScheduler(ctx)
    scheduler.stop()


def cmd_batch_retry_tasks(args):
    """提取未完成任务"""
    import json
    import shutil
    from .batch_workflow import BatchScheduler
    from .contexts import BatchContext
    from .utils import get_existing_batch_count, get_next_backup_index
    from .utils.concurrency import atomic_write_json

    config_path = validate_path(args.config, must_exist=True)
    workdir = (
        validate_path(args.workdir, base_dir=config_path.parent)
        if args.workdir
        else config_path.parent
    )

    ctx = BatchContext(
        config_path=config_path,
        workflow_root=workdir,
        batch_size=100,
    )

    scheduler = BatchScheduler(ctx)
    output_file = validate_path(args.output, base_dir=workdir) if args.output else None
    result = scheduler.extract_retry_tasks(output_file=output_file)

    # 如果指定了 --run 参数，自动启动新批次
    if args.run:
        existing_count = get_existing_batch_count(workdir)
        print(f"\n正在启动新批次，从 batch.{existing_count:05d} 开始...")

        retry_file = (
            Path(args.output).resolve()
            if args.output
            else workdir / "todo_list_retry.json"
        )
        todo_file = workdir / "todo_list.json"

        if retry_file.exists():
            # 备份当前 todo_list.json
            if todo_file.exists():
                next_idx = get_next_backup_index(workdir)
                backup_file = workdir / f"todo_list.origin.{next_idx:03d}"
                shutil.copy(todo_file, backup_file)
                print(f"已备份当前任务列表到: {backup_file}")

            # 复制 retry 文件到 todo_list.json
            shutil.copy(retry_file, todo_file)
            print(f"已将 {retry_file} 复制到 {todo_file}")

        # 启动新批次 - 重置状态以触发重新初始化
        state_file = workdir / "batch_state.json"
        if state_file.exists():
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            state.update(
                {
                    "initialized": False,
                    "start_batch_index": existing_count,
                    "current_batch": existing_count,
                    "current_stage": "olp",
                    "completed_batches": [],
                    "total_batches": 0,
                    "olp_completed": False,
                    "infer_completed": False,
                    "calc_completed": False,
                    "current_job_id": None,
                }
            )
            atomic_write_json(state_file, state)
            print(f"已重置状态，将从 batch.{existing_count:05d} 开始")

        ctx_run = BatchContext(
            config_path=config_path,
            workflow_root=workdir,
            batch_size=args.batch_size if args.batch_size else 100,
            fresh=False,
        )
        scheduler_run = BatchScheduler(ctx_run)
        result_run = scheduler_run.run()
        print(f"新批次完成: {result_run}")


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
    parser_batch.add_argument(
        "--batch-mode",
        choices=["auto", "append", "overwrite"],
        default="auto",
        help="批次处理模式: auto(检测到已有批次时提示), append(追加), overwrite(覆盖)",
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

    parser_batch_retry = subparsers.add_parser(
        "batch-retry-tasks", help="提取未完成任务"
    )
    parser_batch_retry.add_argument(
        "--config",
        required=True,
        help="Path to global_config.yaml",
    )
    parser_batch_retry.add_argument("--workdir", help="工作目录")
    parser_batch_retry.add_argument(
        "--output",
        default="todo_list_retry.json",
        help="Output file for retry tasks",
    )
    parser_batch_retry.add_argument(
        "--run",
        action="store_true",
        help="自动启动新批次处理失败任务",
    )
    parser_batch_retry.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="每批次任务数量 (默认: 100，与 --run 配合使用)",
    )
    parser_batch_retry.set_defaults(func=cmd_batch_retry_tasks)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
