#!/usr/bin/env python3
"""工作流管理器 - 自动化三阶段工作流"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    DEFAULT_MAX_RETRIES,
    FOLDERS_FILE,
    GROUP_INFO_FILE,
    GROUP_MAPPING_FILE,
    GROUP_PADDING,
    GROUP_PREFIX,
    HAMLOG_FILE,
)
from .exceptions import AbortException, FailureType
from .monitor import JobMonitor, MonitorConfig, TaskError
from .template_generator import generate_submit_script
from .utils import chunk_records, load_yaml_config, parse_folders_file

STAGES = ["0olp", "1infer", "2calc"]
JOB_NAMES = {"0olp": "B-olp", "1infer": "B-infer", "2calc": "B-calc"}
CHECK_INTERVAL = 60
MAX_RETRY = 3
MAX_BLOCKED_COUNT = 10
MAX_RUNTIME_HOURS = 72
STATE_FILE = "state.json"
LOG_FILE = "workflow.log"
PID_FILE = "pid.workflow"


class WorkflowManager:
    """工作流管理器"""

    def __init__(self, config_path: Path, workdir: Path):
        self.config_path = Path(config_path).resolve()
        self.workdir = Path(workdir).resolve()
        self.state_file = self.workdir / STATE_FILE
        self.log_file = self.workdir / LOG_FILE
        self.pid_file = self.workdir / PID_FILE
        self.config = self._load_config()
        self.monitor = JobMonitor(MonitorConfig(max_retries=DEFAULT_MAX_RETRIES))

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        return load_yaml_config(self.config_path) or {}

    @staticmethod
    def _normalize_python_path(path: str) -> str:
        """规范化 Python 路径，自动补全 python 解释器名"""
        if not path:
            return "python"
        if path.endswith("/"):
            return path + "python"
        return path

    def _init_state(self) -> Dict[str, Any]:
        """初始化状态"""
        return {
            "current_stage": "0olp",
            "start_time": datetime.now().isoformat(),
            "total_retry_count": 0,
            "stages": {
                "0olp": {"status": "pending", "retry_count": 0, "retry_history": []},
                "1infer": {"status": "pending", "retry_count": 0, "retry_history": []},
                "2calc": {"status": "pending", "retry_count": 0, "retry_history": []},
            },
        }

    def _load_state(self) -> Dict[str, Any]:
        """加载状态"""
        if not self.state_file.exists():
            return self._init_state()

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    state = json.load(f)
                    if "monitor" in state:
                        self.monitor.restore_from_state(state["monitor"])
                    return state
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception:
            return self._init_state()

    def _save_state(self, state: Dict[str, Any]) -> None:
        """保存状态"""
        state["last_update"] = datetime.now().isoformat()
        state["monitor"] = self.monitor.save_state()
        temp_file = self.state_file.with_suffix(".tmp")

        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(state, f, indent=2, ensure_ascii=False)
                    f.flush()
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            temp_file.replace(self.state_file)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise

    def _run_command(
        self, cmd: str, check: bool = False
    ) -> subprocess.CompletedProcess:
        """执行命令"""
        return subprocess.run(
            cmd, shell=True, capture_output=True, text=True, check=check
        )

    def _get_running_jobs(self, stage_name: str) -> List[str]:
        """获取运行中的作业"""
        job_name = JOB_NAMES.get(stage_name)
        if not job_name:
            return []

        user = os.environ.get("USER", "")
        cmd = f"squeue -u {user} -n '{job_name}' -h --format='%i'"
        result = self._run_command(cmd)
        if result.returncode != 0:
            return []

        return [jid.strip() for jid in result.stdout.strip().split("\n") if jid.strip()]

    def _get_all_user_jobs(self) -> Dict[str, str]:
        """获取用户所有作业"""
        cmd = "squeue -u $USER -h --format='%i %j'"
        result = self._run_command(cmd)
        if result.returncode != 0:
            return {}

        jobs = {}
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    jobs[parts[0]] = parts[1]
        return jobs

    def _check_slurm_job_state(self, job_id: str) -> str:
        """检查作业状态"""
        if not job_id:
            return "UNKNOWN"

        main_job_id = job_id.split("_")[0]
        cmd = f"sacct -j {main_job_id} --format=State --noheader --parsertype"
        result = self._run_command(cmd)
        if result.returncode != 0:
            return "UNKNOWN"

        states = [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
        return states[0] if states else "UNKNOWN"

    def _check_prerequisites(self, stage_name: str) -> Tuple[bool, str]:
        """检查前置条件"""
        if stage_name == "0olp":
            if not (self.workdir / "todo_list.json").exists():
                return False, "todo_list.json 不存在"
        elif stage_name == "1infer":
            if not (self.workdir / "0olp" / FOLDERS_FILE).exists():
                return False, "0olp/folders.dat 不存在，请先完成 0olp 阶段"
        elif stage_name == "2calc":
            if not (self.workdir / "1infer" / HAMLOG_FILE).exists():
                return False, "1infer/hamlog.dat 不存在，请先完成 1infer 阶段"
        return True, ""

    def _validate_output_files(self, stage_name: str) -> bool:
        """验证输出文件"""
        output_files = {
            "0olp": self.workdir / "0olp" / FOLDERS_FILE,
            "1infer": self.workdir / "1infer" / HAMLOG_FILE,
            "2calc": self.workdir / "2calc" / FOLDERS_FILE,
        }
        output_file = output_files.get(stage_name)
        return output_file and output_file.exists() and output_file.stat().st_size > 0

    def _load_labels_from_json(self, file_path: Path) -> set:
        """从JSON文件加载标签"""
        if not file_path.exists():
            return set()

        labels = set()
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    labels.add(data.get("path", ""))
                except json.JSONDecodeError:
                    continue
        return labels

    def _load_labels_from_folders(self, file_path: Path) -> set:
        """从folders.dat加载标签"""
        if not file_path.exists():
            return set()

        labels = set()
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts:
                    labels.add(parts[0])
        return labels

    def _get_input_output_info(self, stage_name: str) -> Dict[str, Any]:
        """获取输入输出信息"""
        info = {
            "input_file": None,
            "output_file": None,
            "input_count": 0,
            "output_count": 0,
            "missing_count": 0,
        }

        input_output_map = {
            "0olp": ("todo_list.json", f"0olp/{FOLDERS_FILE}"),
            "1infer": (f"0olp/{FOLDERS_FILE}", f"1infer/{HAMLOG_FILE}"),
            "2calc": (f"1infer/{HAMLOG_FILE}", f"2calc/{FOLDERS_FILE}"),
        }

        if stage_name not in input_output_map:
            return info

        input_file, output_file = input_output_map[stage_name]
        input_path = self.workdir / input_file
        output_path = self.workdir / output_file

        info["input_file"] = str(input_path)
        info["output_file"] = str(output_path)

        if stage_name == "0olp":
            input_labels = self._load_labels_from_json(input_path)
        else:
            input_labels = self._load_labels_from_folders(input_path)

        output_labels = self._load_labels_from_folders(output_path)

        info["input_count"] = len(input_labels)
        info["output_count"] = len(output_labels)
        info["missing_count"] = len(input_labels - output_labels)

        return info

    def _check_stage_status(self, stage_name: str) -> Tuple[str, Dict[str, Any]]:
        """检查阶段状态"""
        details = {}

        prereq_ok, prereq_msg = self._check_prerequisites(stage_name)
        if not prereq_ok:
            return "blocked", {"reason": prereq_msg}

        running_jobs = self._get_running_jobs(stage_name)
        if running_jobs:
            job_id = running_jobs[0]
            job_state = self._check_slurm_job_state(job_id)

            if job_state in ["FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL"]:
                return "failed", {
                    "job_ids": running_jobs,
                    "job_state": job_state,
                    "reason": f"作业失败: {job_state}",
                }

            return "running", {"job_ids": running_jobs}

        if self._validate_output_files(stage_name):
            info = self._get_input_output_info(stage_name)
            details.update(info)

            if info["missing_count"] == 0:
                return "completed", details
            else:
                return "partial", details

        state = self._load_state()
        stage_info = state.get("stages", {}).get(stage_name, {})
        if stage_info.get("job_id"):
            job_state = self._check_slurm_job_state(stage_info["job_id"])
            if job_state in ["FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL"]:
                return "failed", {
                    "job_id": stage_info["job_id"],
                    "job_state": job_state,
                    "reason": f"作业失败: {job_state}",
                }

        return "pending", details

    def _submit_job(self, stage_name: str) -> Optional[str]:
        """提交作业"""
        stage_dir = self.workdir / stage_name
        stage_dir.mkdir(parents=True, exist_ok=True)

        stage_config = self.config.get(stage_name, {})
        software_config = self.config.get("software", {})

        if stage_name == "1infer":
            python_path = self._normalize_python_path(
                software_config.get("python_deeph", "python")
            )
        else:
            python_path = self._normalize_python_path(
                software_config.get("python", "python")
            )

        if stage_name == "1infer":
            self._prepare_infer_groups(stage_dir)

        script_path = generate_submit_script(
            stage_name=stage_name,
            stage_dir=stage_dir,
            stage_config=stage_config,
            python_path=python_path,
            config_path=str(self.config_path),
            software_config=software_config,
        )

        result = subprocess.run(
            "sbatch submit.sh",
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(stage_dir),
        )

        if result.returncode != 0:
            self.monitor.report_error(
                TaskError(
                    stage=stage_name,
                    failure_type=FailureType.SUBMIT_FAILED,
                    message=f"sbatch failed: {result.stderr}",
                    timestamp=datetime.now(),
                )
            )
            return None

        output = result.stdout.strip()
        if "Submitted batch job" in output:
            job_id = output.split()[-1]
            self.monitor.state.job_id = job_id
            return job_id

        return None

    def _prepare_infer_groups(self, stage_dir: Path) -> None:
        """准备推理分组"""
        folders_file = self.workdir / "0olp" / FOLDERS_FILE
        if not folders_file.exists():
            return

        records = parse_folders_file(folders_file)
        infer_config = self.config.get("1infer", {})
        num_groups = infer_config.get("num_groups", 10)
        random_seed = infer_config.get("random_seed", 137)

        groups = chunk_records(records, num_groups, random_seed)

        group_info = []
        for idx, group_records in enumerate(groups, start=1):
            group_id = f"{GROUP_PREFIX}{idx:0{GROUP_PADDING}d}"
            group_info.append(
                {
                    "index": idx,
                    "group_id": group_id,
                    "size": len(group_records),
                    "records": [
                        {
                            "label": r.label,
                            "scf_path": r.scf_path,
                            "geth_path": r.geth_path,
                            "short_path": str(r.short_path),
                        }
                        for r in group_records
                    ],
                }
            )

        info_file = stage_dir / GROUP_INFO_FILE
        mapping_file = stage_dir / GROUP_MAPPING_FILE

        with open(info_file, "w") as f:
            json.dump(group_info, f, indent=2)

        with open(mapping_file, "w") as f:
            for group in group_info:
                for record in group["records"]:
                    f.write(f"{record['label']}\t{group['group_id']}\n")

    def _get_next_stage(self, current: str) -> Optional[str]:
        """获取下一阶段"""
        if current not in STAGES:
            return None
        idx = STAGES.index(current)
        if idx + 1 < len(STAGES):
            return STAGES[idx + 1]
        return None

    def _write_pid(self) -> None:
        """写入PID文件"""
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

    def _remove_pid(self) -> None:
        """删除PID文件"""
        if self.pid_file.exists():
            self.pid_file.unlink()

    def _is_running(self) -> bool:
        """检查是否运行中"""
        if not self.pid_file.exists():
            return False

        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            return False

    def run(self, daemon: bool = False) -> None:
        """运行工作流"""
        import logging

        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(self.log_file, encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )
        logger = logging.getLogger(__name__)

        logger.info("=" * 50)
        logger.info("工作流管理器启动")
        logger.info("=" * 50)

        if self._is_running():
            print("已有实例运行中，请先使用 stop 停止")
            return

        state = self._load_state()
        start_time = datetime.now()
        blocked_count = 0

        for stage in STAGES:
            if state["stages"].get(stage, {}).get("status") == "max_retry_exceeded":
                logger.info(f"[{stage}] 检测到重试上限，自动重置")
                state["stages"][stage]["status"] = "pending"
                state["stages"][stage]["retry_count"] = 0
                state["current_stage"] = stage
                self._save_state(state)
                break

        def signal_handler(signum, frame):
            logger.info("收到停止信号，正在退出...")
            self._remove_pid()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        self._write_pid()

        try:
            while True:
                if self.monitor.should_abort():
                    logger.error(f"快速失败: {self.monitor.state.abort_reason}")
                    state["status"] = "aborted"
                    state["abort_reason"] = self.monitor.state.abort_reason
                    self._save_state(state)
                    break

                elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600
                if elapsed_hours > MAX_RUNTIME_HOURS:
                    logger.error(f"运行时间超过 {MAX_RUNTIME_HOURS} 小时，自动退出")
                    state["status"] = "timeout"
                    state["end_time"] = datetime.now().isoformat()
                    self._save_state(state)
                    break

                current_stage = state.get("current_stage")

                if current_stage is None:
                    logger.info("所有阶段已完成！")
                    break

                if current_stage not in STAGES:
                    logger.error(f"无效的当前阶段: {current_stage}")
                    break

                status, details = self._check_stage_status(current_stage)
                logger.info(f"[{current_stage}] 状态: {status}")

                if status == "pending":
                    blocked_count = 0
                    retry_count = state["stages"][current_stage].get("retry_count", 0)

                    previous_job_id = state["stages"][current_stage].get("job_id")
                    if previous_job_id:
                        retry_count += 1
                        logger.warning(
                            f"[{current_stage}] 检测到重试 (之前作业: {previous_job_id}, 当前重试次数: {retry_count}/{MAX_RETRY})"
                        )
                        state["stages"][current_stage]["retry_count"] = retry_count

                    if retry_count >= MAX_RETRY:
                        logger.error(f"[{current_stage}] 已达到最大重试次数")
                        state["stages"][current_stage]["status"] = "max_retry_exceeded"
                        state["stages"][current_stage]["end_time"] = (
                            datetime.now().isoformat()
                        )
                        self._save_state(state)
                        state["current_stage"] = None
                        self._save_state(state)
                        break

                    job_id = self._submit_job(current_stage)
                    if job_id:
                        state["stages"][current_stage] = {
                            "status": "running",
                            "job_id": job_id,
                            "retry_count": retry_count,
                            "start_time": datetime.now().isoformat(),
                            "retry_history": state["stages"][current_stage].get(
                                "retry_history", []
                            ),
                        }
                        self._save_state(state)
                    else:
                        if self.monitor.should_abort():
                            logger.error(
                                f"[{current_stage}] 作业提交失败，触发快速失败"
                            )
                            state["status"] = "aborted"
                            state["abort_reason"] = self.monitor.state.abort_reason
                            self._save_state(state)
                            break
                        retry_count += 1
                        state["total_retry_count"] = (
                            state.get("total_retry_count", 0) + 1
                        )
                        state["stages"][current_stage]["retry_count"] = retry_count
                        logger.error(
                            f"[{current_stage}] 作业提交失败 ({retry_count}/{MAX_RETRY})"
                        )
                        self._save_state(state)

                elif status == "running":
                    blocked_count = 0
                    job_ids = details.get("job_ids", [])
                    logger.info(f"[{current_stage}] 作业运行中: {job_ids}")

                elif status == "completed":
                    blocked_count = 0
                    logger.info(f"[{current_stage}] 完成！")
                    state["stages"][current_stage] = {
                        "status": "completed",
                        "end_time": datetime.now().isoformat(),
                        **details,
                        "retry_history": state["stages"][current_stage].get(
                            "retry_history", []
                        ),
                    }
                    state["current_stage"] = self._get_next_stage(current_stage)
                    self._save_state(state)

                elif status == "partial":
                    blocked_count = 0
                    missing_count = details.get("missing_count", 0)
                    logger.warning(
                        f"[{current_stage}] 部分完成，缺失 {missing_count} 条"
                    )
                    state["stages"][current_stage] = {
                        "status": "partial",
                        "end_time": datetime.now().isoformat(),
                        **details,
                        "retry_history": state["stages"][current_stage].get(
                            "retry_history", []
                        ),
                    }
                    state["current_stage"] = self._get_next_stage(current_stage)
                    self._save_state(state)

                elif status == "failed":
                    blocked_count = 0
                    logger.error(
                        f"[{current_stage}] 失败: {details.get('reason', '未知')}"
                    )

                    job_state = details.get("job_state", "")
                    if job_state in ["TIMEOUT", "NODE_FAIL"]:
                        ftype = FailureType.NODE_ERROR
                    else:
                        ftype = FailureType.SLURM_FAILED

                    self.monitor.report_error(
                        TaskError(
                            stage=current_stage,
                            failure_type=ftype,
                            message=details.get("reason", "job failed"),
                            timestamp=datetime.now(),
                        )
                    )

                    if self.monitor.should_abort():
                        logger.error(f"[{current_stage}] 失败次数超过限制，快速失败")
                        state["status"] = "aborted"
                        state["abort_reason"] = self.monitor.state.abort_reason
                        self._save_state(state)
                        break

                    retry_count = (
                        state["stages"][current_stage].get("retry_count", 0) + 1
                    )
                    state["stages"][current_stage]["retry_count"] = retry_count
                    state["total_retry_count"] = state.get("total_retry_count", 0) + 1

                    if retry_count >= MAX_RETRY:
                        state["stages"][current_stage]["status"] = "max_retry_exceeded"
                        state["stages"][current_stage]["end_time"] = (
                            datetime.now().isoformat()
                        )
                        state["current_stage"] = None
                    else:
                        state["stages"][current_stage]["status"] = "pending"

                    self._save_state(state)

                elif status == "blocked":
                    blocked_count += 1
                    reason = details.get("reason", "未知")
                    logger.warning(
                        f"[{current_stage}] 被阻塞: {reason} ({blocked_count})"
                    )

                    if blocked_count > MAX_BLOCKED_COUNT:
                        logger.error(f"[{current_stage}] 阻塞次数超过限制，跳过")
                        state["stages"][current_stage]["status"] = "blocked_timeout"
                        state["stages"][current_stage]["end_time"] = (
                            datetime.now().isoformat()
                        )
                        state["current_stage"] = self._get_next_stage(current_stage)
                        self._save_state(state)
                        blocked_count = 0
                    else:
                        time.sleep(CHECK_INTERVAL * 5)
                        continue

                time.sleep(CHECK_INTERVAL)

        finally:
            self._remove_pid()

        logger.info("工作流管理器退出")

    def show_status(self) -> None:
        """显示状态"""
        print("=== 工作流管理器 ===")

        if not self.pid_file.exists():
            print("进程状态: 未运行\n")
        else:
            try:
                with open(self.pid_file, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                print(f"进程状态: 运行中 (PID: {pid})\n")
            except (ValueError, OSError):
                print("进程状态: 已停止\n")

        if not self.state_file.exists():
            print("=== 工作流状态 ===\n尚未开始运行")
            return

        with open(self.state_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        print("=== 工作流状态 ===")
        print(f"开始时间: {state.get('start_time', 'N/A')}")
        print(f"最后更新: {state.get('last_update', 'N/A')}")
        print(f"当前阶段: {state.get('current_stage', 'N/A')}")

        total_retry = state.get("total_retry_count", 0)
        if total_retry > 0:
            print(f"总重试次数: {total_retry}")
        print()

        status_map = {
            "pending": "等待中",
            "running": "运行中",
            "completed": "完成",
            "partial": "部分完成",
            "failed": "失败",
            "blocked": "阻塞",
            "max_retry_exceeded": "超过重试上限",
        }

        for stage in STAGES:
            stage_info = state.get("stages", {}).get(stage, {})
            status = stage_info.get("status", "pending")
            job_id = stage_info.get("job_id")

            status_display = status_map.get(status, status)
            print(f"{stage}: {status_display}")

            if job_id:
                print(f"  作业 ID: {job_id}")

            retry_count = stage_info.get("retry_count", 0)
            if retry_count > 0:
                print(f"  重试次数: {retry_count}/{MAX_RETRY}")

        running_jobs = self._get_all_user_jobs()
        if running_jobs:
            print(f"\n当前运行中的作业:")
            for job_id, job_name in running_jobs.items():
                print(f"  {job_id}: {job_name}")

    def stop(self) -> None:
        """停止运行"""
        if not self.pid_file.exists():
            print("没有运行中的实例")
            return

        try:
            with open(self.pid_file, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"已发送停止信号到进程 {pid}")
        except (ValueError, OSError) as e:
            print(f"停止失败: {e}")

    def restart(self, daemon: bool = False) -> None:
        """重新开始"""
        if self.state_file.exists():
            self.state_file.unlink()
            print("已删除状态文件，将从头开始")

        self.run(daemon=daemon)
