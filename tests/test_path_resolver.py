"""Tests for PathResolver."""

from pathlib import Path
import pytest

from dlazy.path_resolver import PathResolver, RunPathResolver, BatchPathResolver


class TestPathResolverBase:
    """Tests for PathResolver base class."""

    def test_is_abstract(self):
        """PathResolver should be abstract and not instantiable."""
        with pytest.raises(TypeError):
            PathResolver()


class TestRunPathResolver:
    """Tests for RunPathResolver."""

    def test_olp_paths(self, tmp_path):
        """Test OLP stage paths in run mode."""
        resolver = RunPathResolver(tmp_path)

        assert resolver.get_olp_slurm_dir() == tmp_path / "0olp"
        assert resolver.get_olp_output_dir() == tmp_path / "0olp"
        assert resolver.get_olp_tasks_file() == tmp_path / "0olp" / "olp_tasks.jsonl"
        assert resolver.get_olp_error_file() == tmp_path / "0olp" / "error_tasks.jsonl"
        assert resolver.get_olp_folders_file() == tmp_path / "0olp" / "folders.dat"

    def test_infer_paths(self, tmp_path):
        """Test Infer stage paths in run mode."""
        resolver = RunPathResolver(tmp_path)

        assert resolver.get_infer_slurm_dir() == tmp_path / "1infer"
        assert resolver.get_infer_output_dir() == tmp_path / "1infer"
        assert (
            resolver.get_infer_tasks_file() == tmp_path / "1infer" / "infer_tasks.jsonl"
        )
        assert resolver.get_infer_input_source() == tmp_path / "0olp" / "folders.dat"
        assert resolver.get_infer_hamlog_file() == tmp_path / "1infer" / "hamlog.dat"

    def test_calc_paths(self, tmp_path):
        """Test Calc stage paths in run mode."""
        resolver = RunPathResolver(tmp_path)

        assert resolver.get_calc_slurm_dir() == tmp_path / "2calc"
        assert resolver.get_calc_output_dir() == tmp_path / "2calc"
        assert resolver.get_calc_tasks_file() == tmp_path / "2calc" / "calc_tasks.jsonl"
        assert resolver.get_calc_input_source() == tmp_path / "1infer" / "hamlog.dat"


class TestBatchPathResolver:
    """Tests for BatchPathResolver."""

    def test_batch_olp_paths(self, tmp_path):
        """Test OLP stage paths in batch mode."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)

        assert resolver.get_olp_slurm_dir() == tmp_path / "batch.00000" / "slurm_olp"
        assert resolver.get_olp_output_dir() == tmp_path / "batch.00000" / "output_olp"
        assert (
            resolver.get_olp_tasks_file()
            == tmp_path / "batch.00000" / "slurm_olp" / "olp_tasks.jsonl"
        )

    def test_batch_infer_paths(self, tmp_path):
        """Test Infer stage paths in batch mode."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)

        assert (
            resolver.get_infer_slurm_dir() == tmp_path / "batch.00000" / "slurm_infer"
        )
        assert (
            resolver.get_infer_output_dir() == tmp_path / "batch.00000" / "output_infer"
        )
        assert (
            resolver.get_infer_input_source()
            == tmp_path / "batch.00000" / "output_olp" / "folders.dat"
        )

    def test_batch_calc_paths(self, tmp_path):
        """Test Calc stage paths in batch mode."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)

        assert resolver.get_calc_slurm_dir() == tmp_path / "batch.00000" / "slurm_calc"
        assert (
            resolver.get_calc_output_dir() == tmp_path / "batch.00000" / "output_calc"
        )
        assert (
            resolver.get_calc_input_source()
            == tmp_path / "batch.00000" / "output_infer" / "hamlog.dat"
        )

    def test_batch_index_padding(self, tmp_path):
        """Test batch index is zero-padded."""
        resolver = BatchPathResolver(tmp_path, batch_index=42)

        assert "batch.00042" in str(resolver.get_olp_slurm_dir())

    def test_get_todo_list_file(self, tmp_path):
        """Test todo_list.json path."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)

        assert resolver.get_todo_list_file() == tmp_path / "todo_list.json"

    def test_get_next_batch_resolver(self, tmp_path):
        """Test getting next batch resolver."""
        resolver = BatchPathResolver(tmp_path, batch_index=0)
        next_resolver = resolver.get_next_batch_resolver()

        assert next_resolver.batch_index == 1
        assert "batch.00001" in str(next_resolver.get_olp_slurm_dir())
