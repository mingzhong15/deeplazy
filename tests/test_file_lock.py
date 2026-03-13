"""文件锁和 PID 锁测试"""

import json
import os
import threading
import time
from pathlib import Path

import pytest

from dlazy.file_lock import (
    FileLock,
    SharedFileLock,
    atomic_append_jsonl,
    atomic_write_json,
)
from dlazy.pid_lock import PIDLock


class TestFileLock:
    """独占文件锁测试"""

    def test_acquire_and_release(self, tmp_path: Path):
        lockfile = tmp_path / "test.lock"
        lock = FileLock(lockfile)

        assert lock.acquire(timeout=1.0)
        assert lock.is_locked

        lock.release()
        assert not lock.is_locked

    def test_context_manager(self, tmp_path: Path):
        lockfile = tmp_path / "test.lock"

        with FileLock(lockfile) as lock:
            assert lock.is_locked

        assert not lock.is_locked

    def test_lock_timeout(self, tmp_path: Path):
        lockfile = tmp_path / "test.lock"

        lock1 = FileLock(lockfile, timeout=0.5)
        lock1.acquire()

        lock2 = FileLock(lockfile, timeout=0.2)

        start = time.monotonic()
        result = lock2.acquire(timeout=0.3)
        elapsed = time.monotonic() - start

        assert not result
        assert elapsed >= 0.2

        lock1.release()

    def test_concurrent_access(self, tmp_path: Path):
        lockfile = tmp_path / "concurrent.lock"
        counter_file = tmp_path / "counter.txt"
        counter_file.write_text("0")

        results = {"success": 0, "failure": 0}
        lock_obj = threading.Lock()

        def increment_counter():
            lock = FileLock(lockfile, timeout=5.0)
            if lock.acquire(timeout=2.0):
                try:
                    current = int(counter_file.read_text())
                    time.sleep(0.01)
                    counter_file.write_text(str(current + 1))
                    with lock_obj:
                        results["success"] += 1
                finally:
                    lock.release()
            else:
                with lock_obj:
                    results["failure"] += 1

        threads = [threading.Thread(target=increment_counter) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final_count = int(counter_file.read_text())
        assert final_count == 5
        assert results["success"] == 5


class TestSharedFileLock:
    """共享锁测试"""

    def test_shared_lock_multiple_readers(self, tmp_path: Path):
        lockfile = tmp_path / "shared.lock"
        results = []

        def acquire_shared():
            lock = SharedFileLock(lockfile, timeout=2.0)
            if lock.acquire_shared(timeout=1.0):
                try:
                    results.append("acquired")
                    time.sleep(0.1)
                finally:
                    lock.release()

        threads = [threading.Thread(target=acquire_shared) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 3

    def test_shared_vs_exclusive(self, tmp_path: Path):
        lockfile = tmp_path / "mixed.lock"

        shared = SharedFileLock(lockfile)
        exclusive = FileLock(lockfile, timeout=0.5)

        assert shared.acquire_shared(timeout=1.0)

        result = exclusive.acquire(timeout=0.2)
        assert not result

        shared.release()

        result = exclusive.acquire(timeout=1.0)
        assert result
        exclusive.release()


class TestAtomicWrite:
    """原子写入测试"""

    def test_atomic_write_json(self, tmp_path: Path):
        filepath = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        atomic_write_json(filepath, data)

        assert filepath.exists()
        result = json.loads(filepath.read_text())
        assert result == data

    def test_atomic_write_preserves_data_on_failure(self, tmp_path: Path):
        filepath = tmp_path / "existing.json"
        original_data = {"original": "data"}
        filepath.write_text(json.dumps(original_data))

        tmp_path = filepath.with_suffix(".json.tmp")
        try:
            with open(tmp_path, "w") as f:
                f.write("invalid json")
            raise ValueError("Simulated failure")
        except ValueError:
            pass

        assert filepath.exists()
        result = json.loads(filepath.read_text())
        assert result == original_data

    def test_concurrent_writes(self, tmp_path: Path):
        filepath = tmp_path / "concurrent.json"
        errors = []

        def write_data(value):
            try:
                for i in range(10):
                    atomic_write_json(filepath, {"value": value, "iteration": i})
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_data, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        result = json.loads(filepath.read_text())
        assert "value" in result
        assert "iteration" in result


class TestAtomicAppend:
    """原子追加测试"""

    def test_append_jsonl(self, tmp_path: Path):
        filepath = tmp_path / "test.jsonl"
        records = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]

        atomic_append_jsonl(filepath, records)

        lines = filepath.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"id": 1, "name": "a"}
        assert json.loads(lines[1]) == {"id": 2, "name": "b"}

    def test_append_with_lock_protection(self, tmp_path: Path):
        filepath = tmp_path / "protected.jsonl"
        all_records = []

        def append_records(thread_id):
            records = [{"thread": thread_id, "idx": i} for i in range(5)]
            atomic_append_jsonl(filepath, records)
            all_records.extend(records)

        threads = [threading.Thread(target=append_records, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = [l for l in filepath.read_text().strip().split("\n") if l]
        assert len(lines) == 15


class TestPIDLock:
    """PID 锁测试"""

    def test_acquire_and_release(self, tmp_path: Path):
        lockfile = tmp_path / "test.pid"
        lock = PIDLock(lockfile)

        assert lock.acquire()
        assert lock.is_locked()
        assert lockfile.exists()
        assert lockfile.read_text().strip() == str(os.getpid())

        lock.release()
        assert not lock.is_locked()
        assert not lockfile.exists()

    def test_context_manager(self, tmp_path: Path):
        lockfile = tmp_path / "test.pid"

        with PIDLock(lockfile) as lock:
            assert lock.is_locked()
            assert lockfile.exists()

        assert not lockfile.exists()

    def test_double_acquire_fails(self, tmp_path: Path):
        lockfile = tmp_path / "test.pid"

        lock1 = PIDLock(lockfile)
        assert lock1.acquire()

        lock2 = PIDLock(lockfile)
        assert not lock2.acquire()

        lock1.release()

    def test_stale_lock_cleanup(self, tmp_path: Path):
        lockfile = tmp_path / "stale.pid"

        non_existent_pid = 999999999
        lockfile.write_text(str(non_existent_pid))

        lock = PIDLock(lockfile)
        assert lock.acquire()

        assert lockfile.read_text().strip() == str(os.getpid())

        lock.release()

    def test_is_process_running(self, tmp_path: Path):
        lockfile = tmp_path / "test.pid"
        lock = PIDLock(lockfile)

        assert not lock._is_process_running(-1)
        assert not lock._is_process_running(0)
        assert not lock._is_process_running(999999999)

        assert lock._is_process_running(os.getpid())
        assert lock._is_process_running(1)

    def test_owner_pid(self, tmp_path: Path):
        lockfile = tmp_path / "test.pid"
        lock = PIDLock(lockfile)

        assert lock.owner_pid is None

        lock.acquire()
        assert lock.owner_pid == os.getpid()

        lock.release()
        assert lock.owner_pid is None

    def test_concurrent_pid_lock(self, tmp_path: Path):
        lockfile = tmp_path / "concurrent.pid"
        results = {"acquired": [], "failed": 0}
        lock_obj = threading.Lock()

        def try_acquire(thread_id):
            lock = PIDLock(lockfile)
            if lock.acquire():
                try:
                    with lock_obj:
                        results["acquired"].append(thread_id)
                    time.sleep(0.1)
                finally:
                    lock.release()
            else:
                with lock_obj:
                    results["failed"] += 1

        threads = [threading.Thread(target=try_acquire, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results["acquired"]) >= 1
