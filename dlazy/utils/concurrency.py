"""并发安全工具 - 文件锁、进程锁、原子操作、文件操作优化"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import logging

logger = logging.getLogger("dlazy.concurrency")


class FileLock:
    """独占文件锁，支持超时"""

    def __init__(self, filepath: Union[Path, str], timeout: float = 30.0):
        self.filepath = Path(filepath)
        self.timeout = timeout
        self._fd: Optional[int] = None
        self._locked = False

    def acquire(self, timeout: Optional[float] = None) -> bool:
        timeout = timeout if timeout is not None else self.timeout
        lockfile = self.filepath.with_suffix(self.filepath.suffix + ".lock")
        lockfile.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.monotonic()
        while True:
            try:
                self._fd = os.open(str(lockfile), os.O_CREAT | os.O_RDWR, 0o644)
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._locked = True
                logger.debug("获取文件锁成功: %s", lockfile)
                return True
            except (IOError, OSError):
                if self._fd is not None:
                    try:
                        os.close(self._fd)
                    except OSError:
                        pass
                    self._fd = None

                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    logger.warning("获取文件锁超时: %s", lockfile)
                    return False

                time.sleep(0.05)

    def release(self) -> None:
        if self._fd is not None and self._locked:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                logger.debug("释放文件锁成功: %s", self.filepath)
            except OSError as e:
                logger.warning("释放文件锁异常: %s", e)
            finally:
                self._fd = None
                self._locked = False

    def __enter__(self) -> "FileLock":
        if not self.acquire():
            raise TimeoutError(f"获取文件锁超时: {self.filepath}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    @property
    def is_locked(self) -> bool:
        return self._locked


class SharedFileLock:
    """共享文件锁，支持多读者"""

    def __init__(self, filepath: Union[Path, str], timeout: float = 30.0):
        self.filepath = Path(filepath)
        self.timeout = timeout
        self._fd: Optional[int] = None
        self._locked = False

    def acquire_shared(self, timeout: Optional[float] = None) -> bool:
        timeout = timeout if timeout is not None else self.timeout
        lockfile = self.filepath.with_suffix(self.filepath.suffix + ".slock")
        lockfile.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.monotonic()
        while True:
            try:
                self._fd = os.open(str(lockfile), os.O_CREAT | os.O_RDWR, 0o644)
                fcntl.flock(self._fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                self._locked = True
                logger.debug("获取共享锁成功: %s", lockfile)
                return True
            except (IOError, OSError):
                if self._fd is not None:
                    try:
                        os.close(self._fd)
                    except OSError:
                        pass
                    self._fd = None

                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    logger.warning("获取共享锁超时: %s", lockfile)
                    return False

                time.sleep(0.05)

    def release(self) -> None:
        if self._fd is not None and self._locked:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
                logger.debug("释放共享锁成功: %s", self.filepath)
            except OSError as e:
                logger.warning("释放共享锁异常: %s", e)
            finally:
                self._fd = None
                self._locked = False

    def __enter__(self) -> "SharedFileLock":
        if not self.acquire_shared():
            raise TimeoutError(f"获取共享锁超时: {self.filepath}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()

    @property
    def is_locked(self) -> bool:
        return self._locked


class PIDLock:
    """进程锁，自动清理陈旧锁"""

    def __init__(self, lockfile: Union[Path, str]):
        self.lockfile = Path(lockfile)
        self.lockfile.parent.mkdir(parents=True, exist_ok=True)
        self._owned = False

    def acquire(self) -> bool:
        if self.lockfile.exists():
            try:
                pid_str = self.lockfile.read_text().strip()
                if pid_str:
                    old_pid = int(pid_str)
                    if self._is_process_running(old_pid):
                        logger.debug("PID 锁被进程 %d 持有", old_pid)
                        return False
                    else:
                        logger.info(
                            "清理陈旧的 PID 锁: %s (PID %d 已不存在)",
                            self.lockfile,
                            old_pid,
                        )
            except (ValueError, OSError) as e:
                logger.warning("读取 PID 锁文件失败: %s", e)

        try:
            self.lockfile.write_text(str(os.getpid()))
            self._owned = True
            logger.debug("获取 PID 锁成功: %s (PID %d)", self.lockfile, os.getpid())
            return True
        except OSError as e:
            logger.warning("写入 PID 锁文件失败: %s", e)
            return False

    def release(self) -> None:
        if not self._owned:
            return

        try:
            current_pid = os.getpid()
            if self.lockfile.exists():
                stored_pid = self.lockfile.read_text().strip()
                if stored_pid == str(current_pid):
                    self.lockfile.unlink()
                    logger.debug("释放 PID 锁成功: %s", self.lockfile)
                else:
                    logger.warning(
                        "PID 锁不属于当前进程，跳过释放 (当前: %d, 存储: %s)",
                        current_pid,
                        stored_pid,
                    )
        except OSError as e:
            logger.warning("释放 PID 锁异常: %s", e)
        finally:
            self._owned = False

    def is_locked(self) -> bool:
        if not self.lockfile.exists():
            return False

        try:
            pid_str = self.lockfile.read_text().strip()
            if not pid_str:
                return False
            pid = int(pid_str)
            return self._is_process_running(pid)
        except (ValueError, OSError):
            return False

    def _is_process_running(self, pid: int) -> bool:
        if pid <= 0:
            return False

        try:
            os.kill(pid, 0)
            return True
        except OSError as err:
            import errno

            if err.errno == errno.ESRCH:
                return False
            elif err.errno == errno.EPERM:
                return True
            else:
                logger.warning("检查进程状态异常: %s", err)
                return False

    @property
    def owner_pid(self) -> Optional[int]:
        if not self.lockfile.exists():
            return None
        try:
            return int(self.lockfile.read_text().strip())
        except (ValueError, OSError):
            return None

    def __enter__(self) -> "PIDLock":
        if not self.acquire():
            owner = self.owner_pid
            raise RuntimeError(f"无法获取 PID 锁: {self.lockfile}, 被 PID {owner} 持有")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


def atomic_write_json(
    filepath: Union[Path, str], data: Dict[str, Any], indent: int = 2
) -> None:
    """原子写入 JSON 文件 - 先写临时文件，然后重命名"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        os.replace(str(tmp_path), str(filepath))
        logger.debug("原子写入 JSON 成功: %s", filepath)
    except Exception as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def atomic_append_jsonl(
    filepath: Union[Path, str],
    records: List[Dict[str, Any]],
    lock: Optional[FileLock] = None,
) -> None:
    """原子追加 JSONL 记录 - 使用文件锁保护"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    should_release = False
    if lock is None:
        lock = FileLock(filepath)
        should_release = True

    if not lock.is_locked:
        if not lock.acquire():
            raise TimeoutError(f"获取文件锁超时: {filepath}")
        should_release = True

    try:
        with open(filepath, "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        logger.debug("原子追加 JSONL 成功: %s, %d 条记录", filepath, len(records))
    finally:
        if should_release and lock.is_locked:
            lock.release()


def smart_symlink(source: Path, target: Path) -> bool:
    """智能创建符号链接，避免重复操作

    Args:
        source: 源路径
        target: 目标符号链接路径

    Returns:
        True 如果创建了新链接，False 如果链接已正确存在
    """
    if not source.exists():
        raise FileNotFoundError(f"源路径不存在: {source}")

    if target.exists() or target.is_symlink():
        if target.is_symlink():
            try:
                current_target = target.resolve()
                if current_target == source.resolve():
                    return False
            except OSError:
                pass

        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()

    target.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(source, target)
    return True


def ensure_directory(
    path: Path, clean: bool = False, allowed_files: Optional[Set[str]] = None
) -> None:
    """确保目录存在，可选清理

    Args:
        path: 目录路径
        clean: 是否清理目录
        allowed_files: 允许保留的文件名集合
    """
    if allowed_files is None:
        allowed_files = {".gitkeep", "README.md"}

    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return

    if clean:
        shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)
        return

    existing_files = set(p.name for p in path.iterdir())

    if not existing_files or existing_files.issubset(allowed_files):
        return

    shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def batch_symlink(
    sources_targets: List[tuple], log: Optional[Any] = None
) -> Dict[str, int]:
    """批量创建符号链接

    Args:
        sources_targets: (source, target) 元组列表
        log: 可选的日志记录器

    Returns:
        {'created': n, 'skipped': n, 'failed': n} 统计
    """
    stats = {"created": 0, "skipped": 0, "failed": 0}

    for source, target in sources_targets:
        try:
            if smart_symlink(Path(source), Path(target)):
                stats["created"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            stats["failed"] += 1
            if log:
                log.warning("链接失败 %s -> %s: %s", source, target, e)

    if log:
        log.info(
            "批量链接完成: created=%d, skipped=%d, failed=%d",
            stats["created"],
            stats["skipped"],
            stats["failed"],
        )

    return stats
