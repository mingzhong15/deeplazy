"""命令执行器 - 封装各阶段的命令执行逻辑"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Dict, Tuple, Any, List

from .utils import (
    validate_h5,
    ensure_directory,
    write_text,
    run_subprocess,
    generate_random_paths,
)
from .constants import (
    OVERLAP_FILENAME,
    HAMILTONIAN_FILENAME,
    HAMILTONIAN_PRED_FILENAME,
    HAMILTONIAN_LINK_FILENAME,
    INPUTS_SUBDIR,
    OUTPUTS_SUBDIR,
    CONFIG_SUBDIR,
    GETH_SUBDIR,
    DFT_SUBDIR,
    GETH_NEW_SUBDIR,
    AUX_FILENAMES,
    INFER_TEMPLATE,
)
from .exceptions import (
    TransformError,
    InferError,
    GroupNotFoundError,
    HamiltonianNotFoundError,
)

if TYPE_CHECKING:
    from .contexts import OLPContext, InferContext, CalcContext


class OLPCommandExecutor:
    """OLP阶段命令执行器"""

    @staticmethod
    def execute(poscar_path: str, ctx: OLPContext) -> Tuple[str, str]:
        """
        执行单个OLP计算任务

        Args:
            poscar_path: POSCAR文件路径
            ctx: OLP上下文

        Returns:
            (status, label) - status: success/failed/node_error/skipped
        """
        # 检查节点错误标记
        if ctx.node_error_flag and ctx.node_error_flag.exists():
            return ("skipped", Path(poscar_path).name)

        label = Path(poscar_path).name
        write_text(ctx.progress_file, f"{label} start\n", append=True)

        # 生成随机路径
        scf_path, geth_path = generate_random_paths(ctx.result_dir)

        # 创建目录
        ensure_directory(scf_path)
        ensure_directory(geth_path)

        result_line = f"{label} {scf_path} {geth_path}"

        try:
            env = os.environ.copy()
            ntasks = ctx.num_cores // ctx.max_processes

            # 1. 创建输入文件
            command_create = ctx.config["commands"]["create_infile"].format(
                poscar=poscar_path,
                scf=scf_path,
            )
            subprocess.run(command_create, env=env, shell=True, check=True, text=True)

            # 2. 运行OpenMX（带节点错误检测）
            os.chdir(scf_path)
            node_error_detected = OLPCommandExecutor._run_openmx_with_monitor(
                ctx.config["commands"]["run_openmx"], ntasks=ntasks
            )

            if node_error_detected:
                write_text(ctx.progress_file, f"{label} error\n", append=True)
                if ctx.node_error_flag and not ctx.node_error_flag.exists():
                    ctx.node_error_flag.touch()
                return ("node_error", label)

            # 3. 提取overlap
            os.chdir(geth_path)
            command_get = ctx.config["commands"]["extract_overlap"].format(scf=scf_path)
            subprocess.run(command_get, env=env, shell=True, check=True, text=True)

            # 4. 验证结果
            overlaps_file = geth_path / OVERLAP_FILENAME
            ok, message = validate_h5(overlaps_file)

            if not ok:
                write_text(ctx.progress_file, f"{label} error\n", append=True)
                write_text(ctx.error_file, f"hamerror {result_line}\n", append=True)
                return ("failed", label)

            # 5. 记录成功
            write_text(ctx.progress_file, f"{label} end\n", append=True)
            write_text(ctx.folders_file, f"{result_line}\n", append=True)
            return ("success", label)

        except Exception as e:
            write_text(ctx.progress_file, f"{label} error\n", append=True)
            write_text(
                ctx.error_file, f"exception {result_line}: {str(e)}\n", append=True
            )
            return ("failed", label)

    @staticmethod
    def _run_openmx_with_monitor(command_template: str, ntasks: int) -> bool:
        """
        运行OpenMX并监控节点错误

        Returns:
            True if node error detected, False otherwise
        """
        command = command_template.format(ntasks=ntasks)

        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=open("openmx.std", "w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            text=True,
        )

        node_error_detected = False

        def monitor_output():
            nonlocal node_error_detected
            with open("openmx.std", "r", encoding="utf-8") as f:
                while proc.poll() is None:
                    line = f.readline()
                    if not line:
                        continue
                    if "Requested nodes are busy" in line or "Socket timed out" in line:
                        node_error_detected = True
                        proc.terminate()
                        return

        monitor_thread = Thread(target=monitor_output, daemon=True)
        monitor_thread.start()
        proc.wait()
        monitor_thread.join()

        return node_error_detected


class InferCommandExecutor:
    """Infer阶段命令执行器"""

    @staticmethod
    def execute(group_index: int, ctx: InferContext) -> Dict[str, Any]:
        """
        执行单个Infer组计算

        Args:
            group_index: 组索引（1-based）
            ctx: Infer上下文

        Returns:
            执行结果

        Raises:
            GroupNotFoundError: 组不存在
            TransformError: 格式转换失败
            InferError: 推理失败
        """
        # 加载组信息
        group = InferCommandExecutor._load_group_info(ctx.group_info_file, group_index)
        records = group["records"]

        # 准备目录
        input_dir = ctx.result_dir / INPUTS_SUBDIR / group["group_id"]
        output_dir = ctx.result_dir / OUTPUTS_SUBDIR / group["group_id"]
        config_dir = ctx.result_dir / CONFIG_SUBDIR

        ensure_directory(input_dir / GETH_SUBDIR)
        ensure_directory(input_dir / DFT_SUBDIR)
        ensure_directory(output_dir)
        ensure_directory(config_dir)

        # 第一步：Link OLP + Transform
        InferCommandExecutor._link_overlap_files(records, input_dir / GETH_SUBDIR, ctx)
        InferCommandExecutor._run_transform(
            ctx.config["commands"]["transform"],
            input_dir / GETH_SUBDIR,
            input_dir / DFT_SUBDIR,
            ctx.parallel,
        )

        # 第二步：Infer
        config_path = InferCommandExecutor._generate_infer_config(
            ctx, group["group_id"], input_dir, output_dir
        )
        InferCommandExecutor._run_infer(ctx.config["commands"]["infer"], config_path)

        # 第三步：Link Infer + Reverse Transform + Hamlog
        infer_output_dir = InferCommandExecutor._find_latest_output(output_dir)
        InferCommandExecutor._link_infer_outputs(
            records,
            infer_output_dir / DFT_SUBDIR,
            output_dir / GETH_NEW_SUBDIR,
            input_dir / DFT_SUBDIR,
        )
        InferCommandExecutor._run_transform(
            ctx.config["commands"]["transform_reverse"],
            output_dir / GETH_NEW_SUBDIR,
            ctx.result_dir / GETH_SUBDIR,
            ctx.parallel,
            reverse=True,
        )
        InferCommandExecutor._append_hamlog(
            records, ctx.result_dir / GETH_SUBDIR, ctx.hamlog_file
        )

        return {"group_id": group["group_id"], "status": "success"}

    @staticmethod
    def _load_group_info(group_info_file: Path, group_index: int) -> Dict:
        """加载组信息"""
        with open(group_info_file, "r", encoding="utf-8") as handle:
            group_info = json.load(handle)
        for item in group_info:
            if item["index"] == group_index:
                return item
        raise GroupNotFoundError(
            f"group index {group_index} not found in {group_info_file}"
        )

    @staticmethod
    def _link_overlap_files(records: List[Dict], target_root: Path, ctx: InferContext):
        """链接overlap文件"""
        ensure_directory(target_root)

        failures = []
        for record in records:
            short_path = Path(record["short_path"])
            target_dir = target_root / short_path
            ensure_directory(target_dir)

            # 链接overlap文件
            source_file = Path(record["geth_path"]) / OVERLAP_FILENAME
            target_file = target_dir / OVERLAP_FILENAME

            try:
                if source_file.exists():
                    if target_file.exists() or target_file.is_symlink():
                        target_file.unlink()
                    os.symlink(source_file, target_file)
                else:
                    failures.append(str(source_file))
            except Exception as e:
                failures.append(f"{source_file}: {e}")

        # 验证
        for record in records:
            short_path = Path(record["short_path"])
            target_file = target_root / short_path / OVERLAP_FILENAME
            ok, message = validate_h5(target_file)
            if not ok:
                failures.append(f"validation failed: {target_file}")

        if failures:
            raise TransformError(f"Link overlap失败: {failures[:5]}")

    @staticmethod
    def _run_transform(
        command_template: str,
        input_dir: Path,
        output_dir: Path,
        parallel: int,
        reverse: bool = False,
    ):
        """运行格式转换"""
        ensure_directory(output_dir)
        command = command_template.format(
            input_dir=input_dir, output_dir=output_dir, parallel=parallel
        )
        run_subprocess(command, shell=True)

    @staticmethod
    def _generate_infer_config(
        ctx: InferContext, group_id: str, input_dir: Path, output_dir: Path
    ) -> Path:
        """生成推理配置文件"""
        template_path = ctx.workdir / INFER_TEMPLATE
        if not template_path.exists():
            raise InferError(f"模板文件不存在: {template_path}")

        content = template_path.read_text(encoding="utf-8")
        config_content = content.format(
            inputs_dir=str(input_dir),
            outputs_dir=str(output_dir),
            dataset_name=f"{ctx.dataset_prefix}{group_id}",
            model_dir=str(ctx.model_dir),
        )

        config_path = ctx.result_dir / CONFIG_SUBDIR / f"infer_{group_id}.toml"
        write_text(config_path, config_content)
        return config_path

    @staticmethod
    def _run_infer(command_template: str, config_path: Path):
        """运行推理"""
        command = command_template.format(config_path=config_path)
        run_subprocess(command, shell=True)

    @staticmethod
    def _find_latest_output(output_root: Path) -> Path:
        """找到最新的推理输出目录"""
        if not output_root.exists():
            raise InferError(f"推理输出目录不存在: {output_root}")

        subdirs = [item for item in output_root.iterdir() if item.is_dir()]
        if not subdirs:
            raise InferError(f"推理输出目录为空: {output_root}")

        latest = max(subdirs, key=lambda item: item.stat().st_mtime)
        return latest

    @staticmethod
    def _link_infer_outputs(
        records: List[Dict],
        source_dft_dir: Path,
        target_root: Path,
        input_dft_dir: Path,
    ):
        """链接推理输出"""
        ensure_directory(target_root)

        failures = []
        for record in records:
            short_path = Path(record["short_path"])
            source_dir = source_dft_dir / short_path
            target_dir = target_root / short_path
            ensure_directory(target_dir)

            # 链接预测的哈密顿量
            source_ham = source_dir / HAMILTONIAN_PRED_FILENAME
            target_ham = target_dir / HAMILTONIAN_LINK_FILENAME

            try:
                if source_ham.exists():
                    if target_ham.exists() or target_ham.is_symlink():
                        target_ham.unlink()
                    os.symlink(source_ham, target_ham)
                else:
                    failures.append(str(source_ham))
            except Exception as e:
                failures.append(f"{source_ham}: {e}")

            # 链接辅助文件
            for filename in AUX_FILENAMES:
                source_file = input_dft_dir / short_path / filename
                target_file = target_dir / filename
                try:
                    if source_file.exists():
                        if target_file.exists() or target_file.is_symlink():
                            target_file.unlink()
                        os.symlink(source_file, target_file)
                except Exception as e:
                    failures.append(f"{source_file}: {e}")

        if failures:
            raise InferError(f"Link infer outputs失败: {failures[:5]}")

    @staticmethod
    def _append_hamlog(records: List[Dict], reverse_root: Path, hamlog_file: Path):
        """追加到hamlog"""
        ensure_directory(hamlog_file.parent)

        for record in records:
            target_path = reverse_root / record["short_path"]
            line = f"{record['label']} {target_path}\n"
            write_text(hamlog_file, line, append=True)


class CalcCommandExecutor:
    """Calc阶段命令执行器"""

    @staticmethod
    def execute(task: Tuple[str, str], ctx: CalcContext) -> Tuple[str, str]:
        """
        执行单个重算任务

        Args:
            task: (label, hampath) 元组
            ctx: Calc上下文

        Returns:
            (status, label)
        """
        label, hampath = task

        write_text(ctx.progress_file, f"{label} start\n", append=True)

        # 生成随机路径
        scf_path, geth_path = generate_random_paths(ctx.result_dir)
        ensure_directory(scf_path)
        ensure_directory(geth_path)

        result_line = f"{label} {scf_path} {geth_path}"

        try:
            env = os.environ.copy()

            # 1. 创建输入文件
            command_create = ctx.config["commands"]["create_infile"].format(
                poscar=label,
                scf=scf_path,
            )
            subprocess.run(command_create, env=env, shell=True, check=True, text=True)

            # 2. 链接哈密顿量
            ham_file = Path(hampath) / HAMILTONIAN_FILENAME
            if not ham_file.exists():
                raise HamiltonianNotFoundError(f"Hamiltonian not found: {ham_file}")
            target_ham = scf_path / HAMILTONIAN_FILENAME
            if target_ham.exists() or target_ham.is_symlink():
                target_ham.unlink()
            os.symlink(ham_file, target_ham)

            # 3. 运行计算
            os.chdir(scf_path)
            command_run = ctx.config["commands"]["run_openmx"]
            subprocess.run(command_run, env=env, shell=True, text=True)

            # 后处理
            subprocess.run("cat openmx.out >> openmx.scfout", shell=True, text=True)
            subprocess.run("rm -rf openmx_rst", shell=True, text=True)

            # 4. 检查SCF收敛
            command_check = ctx.config["commands"]["check_conv"].format(scf=scf_path)
            result = subprocess.run(
                command_check, env=env, shell=True, capture_output=True, text=True
            )

            if "False" in result.stdout:
                error_type = "scferror" if "scferror" in result.stdout else "sluerror"
                write_text(ctx.progress_file, f"{label} error\n", append=True)
                write_text(ctx.error_file, f"{error_type} {result_line}\n", append=True)
                return ("failed", label)

            # 5. 提取哈密顿量
            os.chdir(geth_path)
            command_extract = ctx.config["commands"]["extract_hamiltonian"].format(
                scf=scf_path
            )
            subprocess.run(command_extract, env=env, shell=True, text=True)

            # 6. 验证结果
            hamiltonians_file = geth_path / HAMILTONIAN_FILENAME
            ok, message = validate_h5(hamiltonians_file)

            if not ok:
                write_text(ctx.progress_file, f"{label} error\n", append=True)
                write_text(ctx.error_file, f"hamerror {result_line}\n", append=True)
                return ("failed", label)

            # 7. 记录成功
            write_text(ctx.progress_file, f"{label} end\n", append=True)
            write_text(ctx.folders_file, f"{result_line}\n", append=True)
            return ("success", label)

        except Exception as e:
            write_text(ctx.progress_file, f"{label} error\n", append=True)
            write_text(
                ctx.error_file, f"exception {result_line}: {str(e)}\n", append=True
            )
            return ("failed", label)
