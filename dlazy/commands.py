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
    get_logger,
    get_batch_dir,
    get_task_dir,
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
    OLP_SUBDIR,
    INFER_SUBDIR,
    SCF_SUBDIR,
    OLP_TASKS_FILE,
    INFER_TASKS_FILE,
    CALC_TASKS_FILE,
    ERROR_TASKS_FILE,
    TASK_DIR_PREFIX,
    TASK_PADDING,
    PROGRESS_FILE,
)
from .record_utils import (
    OlpTask,
    InferTask,
    CalcTask,
    ErrorTask,
    write_olp_tasks,
    read_olp_tasks,
    write_infer_tasks,
    read_infer_tasks,
    write_calc_tasks,
    read_calc_tasks,
    append_error_task,
)
from .exceptions import (
    TransformError,
    InferError,
    GroupNotFoundError,
    HamiltonianNotFoundError,
)

if TYPE_CHECKING:
    from .contexts import OLPContext, InferContext, CalcContext
    from .path_resolver import BatchPathResolver


def _cleanup_directory(path: Path) -> None:
    """清理目录（包括符号链接）"""
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def _ensure_symlink(source: Path, target: Path) -> None:
    """确保创建符号链接（源可以是文件或目录）"""
    if not source.exists():
        raise FileNotFoundError(f"源路径不存在: {source}")

    ensure_directory(target.parent)
    if target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()

    os.symlink(source, target)


class OLPCommandExecutor:
    """OLP阶段命令执行器"""

    @staticmethod
    def execute(path: str, ctx: OLPContext) -> Tuple[str, str]:
        """
        执行单个OLP计算任务

        Args:
            path: POSCAR文件路径
            ctx: OLP上下文

        Returns:
            (status, label) - status: success/failed/node_error/skipped
        """
        # 检查节点错误标记
        if ctx.node_error_flag and ctx.node_error_flag.exists():
            return ("skipped", Path(path).name)

        label = path
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
                poscar=path,
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

    @staticmethod
    def execute_batch(
        task_index: int,
        task: "OlpTask",
        resolver: "BatchPathResolver",
        config: Dict[str, Any],
    ) -> InferTask:
        """
        Execute single OLP task in batch mode with deterministic paths.

        Args:
            task_index: Task index within batch
            task: OlpTask containing path
            resolver: BatchPathResolver for path resolution
            config: Configuration dict

        Returns:
            InferTask for the output

        Raises:
            Exception: If execution fails
        """
        logger = get_logger(f"batch.olp.task{task_index}")
        logger.info("Processing POSCAR: %s", task.path)

        task_dir = resolver.get_olp_task_dir(task_index)
        ensure_directory(task_dir)

        label = Path(task.path).name
        progress_file = resolver.get_olp_slurm_dir() / PROGRESS_FILE

        def write_progress(msg):
            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(f"{label} {msg}\n")

        write_progress("start")

        try:
            env = os.environ.copy()

            command_create = config["commands"]["create_infile"].format(
                poscar=task.path,
                scf=task_dir,
            )
            subprocess.run(command_create, env=env, shell=True, check=True, text=True)

            os.chdir(task_dir)
            command_openmx = config["commands"]["run_openmx"].format(ntasks=1)
            with open("openmx.std", "w", encoding="utf-8") as f:
                subprocess.run(
                    command_openmx,
                    env=env,
                    shell=True,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

            command_extract = config["commands"]["extract_overlap"].format(scf=task_dir)
            subprocess.run(command_extract, env=env, shell=True, check=True, text=True)

            overlaps_file = task_dir / OVERLAP_FILENAME
            ok, message = validate_h5(overlaps_file)

            if not ok:
                raise Exception(f"Overlap validation failed: {message}")

            logger.info("OLP completed: %s", task_dir)

            write_progress("end")

            return InferTask(
                path=task.path,
                scf_path=str(task_dir),
            )

        except Exception as e:
            logger.error("OLP failed: %s", e)
            write_progress("error")
            raise


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
        logger = get_logger(f"infer.group{group_index}")

        # 加载组信息
        group = InferCommandExecutor._load_group_info(ctx.group_info_file, group_index)
        records = group["records"]

        logger.info(
            "处理组 %s (index=%s, size=%s)",
            group["group_id"],
            group["index"],
            group["size"],
        )

        # 准备目录
        input_dir = ctx.result_dir / INPUTS_SUBDIR / group["group_id"]
        output_dir = ctx.result_dir / OUTPUTS_SUBDIR / group["group_id"]
        config_dir = ctx.result_dir / CONFIG_SUBDIR

        # 清理并创建目录
        _cleanup_directory(input_dir)
        ensure_directory(input_dir / GETH_SUBDIR)
        ensure_directory(input_dir / DFT_SUBDIR)
        _cleanup_directory(output_dir)
        ensure_directory(output_dir)
        ensure_directory(config_dir)

        try:
            # 第一步：Link OLP + Transform
            logger.info("开始 link olp 阶段")
            InferCommandExecutor._link_overlap_files(
                records, input_dir / GETH_SUBDIR, ctx, logger
            )

            logger.info("开始 batch transform 阶段")
            InferCommandExecutor._run_transform(
                ctx.config["commands"]["transform"],
                input_dir / GETH_SUBDIR,
                input_dir / DFT_SUBDIR,
                ctx.parallel,
                logger,
            )

            # 第二步：Infer
            config_path = InferCommandExecutor._generate_infer_config(
                ctx, group["group_id"], input_dir, output_dir, logger
            )
            logger.info("开始 infer 阶段")
            InferCommandExecutor._run_infer(
                ctx.config["commands"]["infer"], config_path, logger
            )

            # 第三步：Link Infer + Reverse Transform + Hamlog
            infer_output_dir = InferCommandExecutor._find_latest_output(
                output_dir, logger
            )
            logger.info("开始 link infer outputs 阶段")
            InferCommandExecutor._link_infer_outputs(
                records,
                infer_output_dir / DFT_SUBDIR,
                output_dir / GETH_NEW_SUBDIR,
                input_dir / DFT_SUBDIR,
                logger,
            )
            logger.info("开始 batch transform reverse 阶段")
            InferCommandExecutor._run_transform(
                ctx.config["commands"]["transform_reverse"],
                output_dir / GETH_NEW_SUBDIR,
                ctx.result_dir / GETH_SUBDIR,
                ctx.parallel,
                logger,
                reverse=True,
            )
            InferCommandExecutor._append_hamlog(
                records, ctx.result_dir / GETH_SUBDIR, ctx.hamlog_file, logger
            )

            logger.info("组 %s 处理完成", group["group_id"])
            return {"group_id": group["group_id"], "status": "success"}

        except Exception as e:
            logger.error("组 %s 处理失败: %s", group["group_id"], str(e))
            # 写入错误文件
            ensure_directory(ctx.error_file.parent)
            error_msg = f"{group['index']} {group['group_id']} {str(e)}"
            write_text(ctx.error_file, f"{error_msg}\n", append=True)
            raise

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
    def _link_overlap_files(
        records: List[Dict], target_root: Path, ctx: InferContext, logger
    ):
        """链接overlap文件（链接整个目录，类似 v2.3）"""
        ensure_directory(target_root)

        logger.info("链接 %d 个 overlap 目录到 %s", len(records), target_root)

        failures = []
        success_count = 0
        for record in records:
            short_path = Path(record["short_path"])
            source_dir = Path(record["geth_path"])
            target = target_root / short_path

            try:
                if source_dir.exists():
                    # 链接整个目录
                    _ensure_symlink(source_dir, target)
                    success_count += 1
                else:
                    failures.append(f"源目录不存在: {source_dir}")
                    logger.warning("源目录不存在: %s", source_dir)
            except Exception as e:
                failures.append(f"{source_dir}: {e}")
                logger.error("链接失败: %s -> %s", source_dir, e)

        logger.info("成功链接 %d/%d 个目录", success_count, len(records))

        # 验证
        logger.info("验证链接文件完整性...")
        validate_failures = []
        for record in records:
            short_path = Path(record["short_path"])
            target_file = target_root / short_path / OVERLAP_FILENAME
            ok, message = validate_h5(target_file)
            if not ok:
                validate_failures.append(f"{target_file}: {message}")
                logger.error("验证失败: %s -> %s", target_file, message)

        all_failures = failures + validate_failures
        if all_failures:
            logger.error("Link overlap 失败，共 %d 个错误", len(all_failures))
            raise TransformError(f"Link overlap失败: {all_failures[:5]}")

        logger.info("Link overlap 完成")

    @staticmethod
    def _run_transform(
        command_template: str,
        input_dir: Path,
        output_dir: Path,
        parallel: int,
        logger,
        reverse: bool = False,
    ):
        """运行格式转换"""
        ensure_directory(output_dir)
        stage_name = "batch_transform_reverse" if reverse else "batch_transform"
        command = command_template.format(
            input_dir=input_dir, output_dir=output_dir, parallel=parallel
        )
        logger.info("[%s] 执行命令: %s", stage_name, command)
        run_subprocess(command, shell=True)

    @staticmethod
    def _generate_infer_config(
        ctx: InferContext, group_id: str, input_dir: Path, output_dir: Path, logger
    ) -> Path:
        """生成推理配置文件"""
        package_dir = Path(__file__).parent
        template_path = package_dir / INFER_TEMPLATE
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
        logger.info("生成推理配置: %s", config_path)
        return config_path

    @staticmethod
    def _run_infer(command_template: str, config_path: Path, logger):
        """运行推理"""
        command = command_template.format(config_path=config_path)
        logger.info("[infer] 执行命令: %s", command)
        run_subprocess(command, shell=True)

    @staticmethod
    def _find_latest_output(output_root: Path, logger) -> Path:
        """找到最新的推理输出目录"""
        if not output_root.exists():
            raise InferError(f"推理输出目录不存在: {output_root}")

        subdirs = [item for item in output_root.iterdir() if item.is_dir()]
        if not subdirs:
            raise InferError(f"推理输出目录为空: {output_root}")

        latest = max(subdirs, key=lambda item: item.stat().st_mtime)
        logger.info("检测到最新推理结果目录: %s", latest)
        return latest

    @staticmethod
    def _link_infer_outputs(
        records: List[Dict],
        source_dft_dir: Path,
        target_root: Path,
        input_dft_dir: Path,
        logger,
    ):
        """链接推理输出"""
        ensure_directory(target_root)
        logger.info("链接推理输出到 %s", target_root)

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
                    failures.append(f"源文件不存在: {source_ham}")
                    logger.warning("Hamiltonian 源文件不存在: %s", source_ham)
            except Exception as e:
                failures.append(f"{source_ham}: {e}")
                logger.error("链接失败: %s -> %s", source_ham, e)

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
                    logger.warning("链接辅助文件失败: %s -> %s", source_file, e)

        if failures:
            for message in failures:
                logger.error("推理结果链接失败: %s", message)
            raise InferError(f"推理结果链接失败: {failures[:5]}")

        logger.info("链接推理输出完成")

    @staticmethod
    def _append_hamlog(
        records: List[Dict], reverse_root: Path, hamlog_file: Path, logger
    ):
        """追加到hamlog"""
        ensure_directory(hamlog_file.parent)

        for record in records:
            target_path = reverse_root / record["short_path"]
            line = f"{record['label']} {target_path}\n"
            write_text(hamlog_file, line, append=True)

        logger.info("已写入 hamlog %d 条记录 -> %s", len(records), hamlog_file)

    @staticmethod
    def execute_batch(
        group_index: int,
        infer_tasks: List[InferTask],
        resolver: "BatchPathResolver",
        config: Dict[str, Any],
        model_dir: Path,
        dataset_prefix: str,
        parallel: int,
    ) -> List[CalcTask]:
        """
        Execute Infer tasks for a group in batch mode with deterministic paths.

        Args:
            group_index: Group index (1-based)
            infer_tasks: List of InferTask for this group
            resolver: BatchPathResolver for path resolution
            config: Configuration dict
            model_dir: Model directory for inference
            dataset_prefix: Dataset prefix for config
            parallel: Parallelism level

        Returns:
            List of CalcTask for the output

        Raises:
            Exception: If execution fails
        """
        logger = get_logger(f"batch.infer.group{group_index}")
        logger.info("Processing group %d with %d tasks", group_index, len(infer_tasks))

        group_dir = resolver.get_infer_group_dir(group_index)
        ensure_directory(group_dir)

        progress_file = resolver.get_infer_slurm_dir() / PROGRESS_FILE

        def write_progress(label, msg):
            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(f"{label} {msg}\n")

        inputs_geth_dir = group_dir / INPUTS_SUBDIR / GETH_SUBDIR
        outputs_dir = group_dir / OUTPUTS_SUBDIR
        final_geth_dir = group_dir / GETH_SUBDIR

        ensure_directory(inputs_geth_dir)
        ensure_directory(outputs_dir)
        ensure_directory(final_geth_dir)

        try:
            for i, infer_task in enumerate(infer_tasks):
                task_dirname = f"{TASK_DIR_PREFIX}.{i:0{TASK_PADDING}d}"
                target_task_dir = inputs_geth_dir / task_dirname

                label = Path(infer_task.path).name
                write_progress(label, "start")

                olp_dir = Path(infer_task.scf_path)

                if not olp_dir.exists():
                    raise FileNotFoundError(f"OLP directory not found: {olp_dir}")

                overlap_file = olp_dir / OVERLAP_FILENAME
                if not overlap_file.exists():
                    raise FileNotFoundError(f"Overlap file not found: {overlap_file}")

                if target_task_dir.exists() or target_task_dir.is_symlink():
                    if target_task_dir.is_symlink():
                        target_task_dir.unlink()
                    else:
                        import shutil

                        shutil.rmtree(target_task_dir)

                os.symlink(olp_dir, target_task_dir)

            logger.info("Linked %d OLP directories", len(infer_tasks))

            input_dft_dir = group_dir / INPUTS_SUBDIR / DFT_SUBDIR
            ensure_directory(input_dft_dir)

            transform_cmd = config["commands"]["transform"]
            command = transform_cmd.format(
                input_dir=inputs_geth_dir,
                output_dir=input_dft_dir,
                parallel=parallel,
            )
            logger.info("Running transform: %s", command)
            run_subprocess(command, shell=True)

            package_dir = Path(__file__).parent
            template_path = package_dir / INFER_TEMPLATE
            content = template_path.read_text(encoding="utf-8")
            config_content = content.format(
                inputs_dir=str(group_dir / INPUTS_SUBDIR),
                outputs_dir=str(outputs_dir),
                dataset_name=f"{dataset_prefix}_g{group_index:03d}",
                model_dir=str(model_dir),
            )
            infer_config_path = group_dir / CONFIG_SUBDIR / "infer.toml"
            ensure_directory(infer_config_path.parent)
            write_text(infer_config_path, config_content)

            infer_cmd = config["commands"]["infer"]
            command = infer_cmd.format(config_path=infer_config_path)
            logger.info("Running infer: %s", command)
            run_subprocess(command, shell=True)

            subdirs = [item for item in outputs_dir.iterdir() if item.is_dir()]
            if not subdirs:
                raise InferError(f"No output directory in {outputs_dir}")
            latest_output = max(subdirs, key=lambda item: item.stat().st_mtime)

            output_dft_dir = latest_output / DFT_SUBDIR
            geth_new_dir = group_dir / GETH_NEW_SUBDIR
            ensure_directory(geth_new_dir)

            calc_tasks = []
            for i, infer_task in enumerate(infer_tasks):
                task_dirname = f"{TASK_DIR_PREFIX}.{i:0{TASK_PADDING}d}"

                source_ham = output_dft_dir / task_dirname / HAMILTONIAN_PRED_FILENAME
                if not source_ham.exists():
                    raise InferError(f"Predicted Hamiltonian not found: {source_ham}")

                target_task_dir = geth_new_dir / task_dirname
                ensure_directory(target_task_dir)
                target_ham = target_task_dir / HAMILTONIAN_LINK_FILENAME
                if target_ham.exists() or target_ham.is_symlink():
                    target_ham.unlink()
                os.symlink(source_ham, target_ham)

                source_info = output_dft_dir / task_dirname / "info.json"
                if source_info.exists():
                    target_info = target_task_dir / "info.json"
                    if target_info.exists() or target_info.is_symlink():
                        target_info.unlink()
                    os.symlink(source_info, target_info)

            transform_reverse_cmd = config["commands"]["transform_reverse"]
            command = transform_reverse_cmd.format(
                input_dir=geth_new_dir,
                output_dir=final_geth_dir,
                parallel=parallel,
            )
            logger.info("Running transform_reverse: %s", command)
            run_subprocess(command, shell=True)

            for i, infer_task in enumerate(infer_tasks):
                task_dirname = f"{TASK_DIR_PREFIX}.{i:0{TASK_PADDING}d}"
                geth_task_dir = final_geth_dir / task_dirname
                ham_file = geth_task_dir / HAMILTONIAN_FILENAME

                ok, message = validate_h5(ham_file)
                if not ok:
                    raise Exception(
                        f"Hamiltonian validation failed for task {i}: {message}"
                    )

                calc_tasks.append(
                    CalcTask(
                        path=infer_task.path,
                        geth_path=str(geth_task_dir),
                    )
                )

            logger.info("Infer completed for group %d", group_index)
            return calc_tasks

        except Exception as e:
            logger.error("Infer failed: %s", e)
            raise


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

    @staticmethod
    def execute_batch(
        task_index: int,
        task: CalcTask,
        resolver: "BatchPathResolver",
        config: Dict[str, Any],
    ) -> Tuple[str, str]:
        """
        Execute single Calc task in batch mode with deterministic paths.

        Args:
            task_index: Task index within batch
            task: CalcTask from Infer stage
            resolver: BatchPathResolver for path resolution
            config: Configuration dict

        Returns:
            (status, label) tuple

        Raises:
            Exception: If execution fails
        """
        logger = get_logger(f"batch.calc.task{task_index}")
        logger.info("Processing CalcTask: %s", task.path)

        task_dir = resolver.get_calc_task_dir(task_index)
        scf_dir = task_dir / SCF_SUBDIR
        geth_dir = task_dir / GETH_SUBDIR
        ensure_directory(scf_dir)
        ensure_directory(geth_dir)

        label = Path(task.path).name
        progress_file = resolver.get_calc_slurm_dir() / PROGRESS_FILE

        def write_progress(msg):
            with open(progress_file, "a", encoding="utf-8") as f:
                f.write(f"{label} {msg}\n")

        write_progress("start")

        try:
            env = os.environ.copy()

            command_create = config["commands"]["create_infile"].format(
                poscar=task.path,
                scf=scf_dir,
            )
            subprocess.run(command_create, env=env, shell=True, check=True, text=True)

            infer_geth_dir = Path(task.geth_path)
            pred_ham = infer_geth_dir / HAMILTONIAN_LINK_FILENAME
            if not pred_ham.exists():
                pred_ham = infer_geth_dir / HAMILTONIAN_PRED_FILENAME
            if not pred_ham.exists():
                raise HamiltonianNotFoundError(
                    f"Hamiltonian not found in {infer_geth_dir}"
                )

            target_ham = scf_dir / HAMILTONIAN_FILENAME
            if target_ham.exists() or target_ham.is_symlink():
                target_ham.unlink()
            os.symlink(pred_ham, target_ham)

            os.chdir(scf_dir)
            command_run = config["commands"]["run_openmx"]
            with open("openmx.std", "a", encoding="utf-8") as f:
                subprocess.run(
                    command_run,
                    env=env,
                    shell=True,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

            subprocess.run("cat openmx.out >> openmx.scfout", shell=True, text=True)
            subprocess.run("rm -rf openmx_rst", shell=True, text=True)

            command_check = config["commands"]["check_conv"].format(scf=scf_dir)
            result = subprocess.run(
                command_check, env=env, shell=True, capture_output=True, text=True
            )

            if "False" in result.stdout:
                error_type = "scferror" if "scferror" in result.stdout else "sluerror"
                logger.error("SCF not converged: %s", error_type)
                write_progress("error")
                return ("failed", label)

            os.chdir(geth_dir)
            command_extract = config["commands"]["extract_hamiltonian"].format(
                scf=scf_dir
            )
            subprocess.run(command_extract, env=env, shell=True, text=True)

            hamiltonians_file = geth_dir / HAMILTONIAN_FILENAME
            ok, message = validate_h5(hamiltonians_file)

            if not ok:
                logger.error("Hamiltonian validation failed: %s", message)
                write_progress("error")
                return ("failed", label)

            logger.info("Calc completed: %s", geth_dir)
            write_progress("end")
            return ("success", label)

        except Exception as e:
            logger.error("Calc failed: %s", e)
            write_progress("error")
            return ("failed", label)
