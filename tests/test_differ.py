"""Tests for the differ module."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from diffmind.differ import Diff, read_stdin_diff


class TestDiff:
    def test_is_empty_true(self):
        d = Diff(label="test", content="   \n  ")
        assert d.is_empty

    def test_is_empty_false(self):
        d = Diff(label="test", content="+ added line")
        assert not d.is_empty

    def test_line_count(self):
        d = Diff(label="test", content="line1\nline2\nline3")
        assert d.line_count == 2  # counts \n characters

    def test_default_fields(self):
        d = Diff(label="x", content="y")
        assert d.base == ""
        assert d.head == ""
        assert d.files_changed == []

    def test_files_changed(self):
        d = Diff(label="x", content="y", files_changed=["a.py", "b.py"])
        assert len(d.files_changed) == 2


class TestReadStdinDiff:
    def test_raises_on_tty(self):
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(ValueError, match="No diff on stdin"):
                read_stdin_diff()

    def test_reads_stdin(self):
        diff_content = "@@ -1,3 +1,4 @@\n line\n+added\n"
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = diff_content
            d = read_stdin_diff()
        assert d.label == "stdin"
        assert d.content == diff_content
        assert not d.is_empty


class TestDiffCommands:
    """Test async diff extraction functions against a mock git process."""

    @pytest.mark.asyncio
    async def test_diff_commits(self):
        from diffmind.differ import diff_commits

        async def fake_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            if "--name-only" in args:
                proc.communicate = AsyncMock(return_value=(b"src/foo.py\n", b""))
            else:
                proc.communicate = AsyncMock(return_value=(b"+added line\n", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_run):
            d = await diff_commits("abc123", "def456")

        assert d.label == "abc123..def456"
        assert d.base == "abc123"
        assert d.head == "def456"
        assert "added" in d.content
        assert "src/foo.py" in d.files_changed

    @pytest.mark.asyncio
    async def test_diff_staged_empty(self):
        from diffmind.differ import diff_staged

        async def fake_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_run):
            d = await diff_staged()

        assert d.label == "staged"
        assert d.is_empty
        assert d.files_changed == []

    @pytest.mark.asyncio
    async def test_git_error_raises(self):
        from diffmind.differ import diff_working

        async def fake_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 128
            proc.communicate = AsyncMock(return_value=(b"", b"not a git repository"))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_run):
            with pytest.raises(RuntimeError, match="not a git repository"):
                await diff_working()
