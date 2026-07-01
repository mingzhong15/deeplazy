"""Unit tests for dlazy.engine: aggregate_status and sid-filter resolution."""
import json
import tempfile
from pathlib import Path

import pytest

from dlazy.engine import Workflow


def _make_workflow(work_dir, summary_lines=None, mode="massive"):
    """Build a Workflow pointing at a work_dir with optional _summary.ndjson."""
    with tempfile.TemporaryDirectory() as pdir:
        param_path = Path(pdir) / "param.json"
        machine_path = Path(pdir) / "machine.json"
        structs = Path(pdir) / "structs.txt"
        structs.touch()
        param = {
            "name": "t", "mode": mode,
            "structures": str(structs),
            "work_dir": str(work_dir),
            "steps": [{"name": "e6", "type": "scf"}],
        }
        param_path.write_text(json.dumps(param))
        machine = {
            "machine": {"batch_type": "Slurm", "context_type": "LocalContext",
                        "local_root": ".", "remote_root": "."},
            "resources": {"number_node": 1, "cpu_per_node": 64,
                            "queue_name": "q", "group_size": 50},
        }
        machine_path.write_text(json.dumps(machine))
        return Workflow(str(param_path), str(machine_path))


def test_aggregate_status_returns_none_when_no_summary():
    with tempfile.TemporaryDirectory() as wd:
        wf = _make_workflow(wd)
        assert wf._aggregate_status("e6") is None


def test_aggregate_status_tallies_ok_fail_with_failed_sids():
    with tempfile.TemporaryDirectory() as wd:
        sd = Path(wd) / "restart" / "e6" / "_status"
        sd.mkdir(parents=True)
        (sd / "_summary.ndjson").write_text(
            '{"sid":"s1","state":"ok"}\n'
            '{"sid":"s2","state":"ok"}\n'
            '{"sid":"s3","state":"fail"}\n'
        )
        wf = _make_workflow(wd)
        stats = wf._aggregate_status("e6")
        assert stats["total"] == 3
        assert stats["ok"] == 2
        assert stats["fail"] == 1
        assert stats["failed_sids"] == {"s3"}


def test_aggregate_status_last_state_wins_for_reruns():
    with tempfile.TemporaryDirectory() as wd:
        sd = Path(wd) / "restart" / "e6" / "_status"
        sd.mkdir(parents=True)
        (sd / "_summary.ndjson").write_text(
            '{"sid":"s1","state":"fail"}\n'
            '{"sid":"s1","state":"ok"}\n'   # rerun fixed it
            '{"sid":"s2","state":"fail"}\n'
        )
        wf = _make_workflow(wd)
        stats = wf._aggregate_status("e6")
        assert stats["ok"] == 1
        assert stats["fail"] == 1
        assert stats["failed_sids"] == {"s2"}


def test_aggregate_status_skips_malformed_lines():
    with tempfile.TemporaryDirectory() as wd:
        sd = Path(wd) / "restart" / "e6" / "_status"
        sd.mkdir(parents=True)
        (sd / "_summary.ndjson").write_text(
            'garbage\n'
            '\n'
            '{"sid":"s1","state":"ok"}\n'
            '{"sid":"" ,"state":"ok"}\n'   # empty sid: skipped
            '{"state":"ok"}\n'             # missing sid: skipped
        )
        wf = _make_workflow(wd)
        stats = wf._aggregate_status("e6")
        assert stats["total"] == 1
        assert stats["ok"] == 1


def test_resolve_sid_filter_only_sids_returns_set():
    with tempfile.TemporaryDirectory() as wd:
        wf = _make_workflow(wd)
        sids, should_return = wf._resolve_sid_filter(None, False, "s1,s2, s3 ,")
        assert sids == {"s1", "s2", "s3"}
        assert should_return is False


def test_resolve_sid_filter_none_when_no_flags():
    with tempfile.TemporaryDirectory() as wd:
        wf = _make_workflow(wd)
        sids, should_return = wf._resolve_sid_filter(None, False, None)
        assert sids is None
        assert should_return is False


def test_resolve_sid_filter_retry_failed_needs_step():
    with tempfile.TemporaryDirectory() as wd:
        wf = _make_workflow(wd)
        sids, should_return = wf._resolve_sid_filter(None, True, None)
        assert should_return is True


def test_resolve_sid_filter_retry_failed_falls_back_when_no_summary():
    with tempfile.TemporaryDirectory() as wd:
        wf = _make_workflow(wd)
        sids, should_return = wf._resolve_sid_filter(
            "e6", True, None)
        assert sids is None
        assert should_return is False


def test_resolve_sid_filter_retry_failed_reads_failed_sids():
    with tempfile.TemporaryDirectory() as wd:
        sd = Path(wd) / "restart" / "e6" / "_status"
        sd.mkdir(parents=True)
        (sd / "_summary.ndjson").write_text(
            '{"sid":"s1","state":"ok"}\n'
            '{"sid":"s2","state":"fail"}\n'
            '{"sid":"s3","state":"fail"}\n'
        )
        wf = _make_workflow(wd)
        sids, should_return = wf._resolve_sid_filter("e6", True, None)
        assert sids == {"s2", "s3"}
        assert should_return is False


def test_resolve_sid_filter_retry_failed_ignored_in_easy_mode():
    with tempfile.TemporaryDirectory() as wd:
        sd = Path(wd) / "restart" / "e6" / "_status"
        sd.mkdir(parents=True)
        (sd / "_summary.ndjson").write_text(
            '{"sid":"s2","state":"fail"}\n'
        )
        wf = _make_workflow(wd, mode="easy")
        sids, should_return = wf._resolve_sid_filter("e6", True, None)
        assert sids is None
        assert should_return is False