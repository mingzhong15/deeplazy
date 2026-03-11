import tempfile
from pathlib import Path

import pytest

from dlazy.record_utils import (
    append_error_task,
    CalcTask,
    ErrorTask,
    InferTask,
    OlpTask,
    read_calc_tasks,
    read_infer_tasks,
    read_olp_tasks,
    write_calc_tasks,
    write_infer_tasks,
    write_olp_tasks,
)


class TestOlpTask:
    def test_olp_task_creation(self):
        task = OlpTask(poscar_path="/path/to/POSCAR")
        assert task.poscar_path == "/path/to/POSCAR"

    def test_olp_task_to_dict(self):
        task = OlpTask(poscar_path="/path/to/POSCAR")
        assert task.to_dict() == {"poscar_path": "/path/to/POSCAR"}

    def test_read_write_olp_tasks(self):
        tasks = [
            OlpTask(poscar_path="/path/a.vasp"),
            OlpTask(poscar_path="/path/b.vasp"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "olp_tasks.jsonl"
            write_olp_tasks(filepath, tasks)
            assert filepath.exists()

            loaded = read_olp_tasks(filepath)
            assert len(loaded) == 2
            assert loaded[0].poscar_path == "/path/a.vasp"
            assert loaded[1].poscar_path == "/path/b.vasp"


class TestInferTask:
    def test_infer_task_creation(self):
        task = InferTask(
            poscar_path="/path/to/POSCAR",
            scf_path="batch.00000/task.000000/olp",
        )
        assert task.poscar_path == "/path/to/POSCAR"
        assert task.scf_path == "batch.00000/task.000000/olp"

    def test_read_write_infer_tasks(self):
        tasks = [
            InferTask(poscar_path="/a.vasp", scf_path="batch.0/task.0/olp"),
            InferTask(poscar_path="/b.vasp", scf_path="batch.0/task.1/olp"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "infer_tasks.jsonl"
            write_infer_tasks(filepath, tasks)
            loaded = read_infer_tasks(filepath)
            assert len(loaded) == 2


class TestCalcTask:
    def test_calc_task_creation(self):
        task = CalcTask(
            poscar_path="/path/to/POSCAR",
            geth_path="batch.00000/task.000000/infer",
        )
        assert task.geth_path == "batch.00000/task.000000/infer"

    def test_read_write_calc_tasks(self):
        tasks = [
            CalcTask(poscar_path="/a.vasp", geth_path="batch.0/task.0/infer"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "calc_tasks.jsonl"
            write_calc_tasks(filepath, tasks)
            loaded = read_calc_tasks(filepath)
            assert len(loaded) == 1


class TestErrorTask:
    def test_error_task_creation(self):
        task = ErrorTask(
            poscar_path="/path/to/POSCAR",
            stage="olp",
            error="openmx failed",
            batch_id="00000",
            task_id="000000",
        )
        assert task.stage == "olp"
        assert task.error == "openmx failed"

    def test_append_error_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "error_tasks.jsonl"
            append_error_task(
                filepath,
                ErrorTask(
                    poscar_path="/a.vasp",
                    stage="olp",
                    error="err1",
                    batch_id="0",
                    task_id="0",
                ),
            )
            append_error_task(
                filepath,
                ErrorTask(
                    poscar_path="/b.vasp",
                    stage="infer",
                    error="err2",
                    batch_id="0",
                    task_id="1",
                ),
            )
            with open(filepath) as f:
                lines = f.readlines()
            assert len(lines) == 2
