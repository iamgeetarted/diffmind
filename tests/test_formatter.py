"""Tests for the formatter module."""

from __future__ import annotations

import json

import pytest

from diffmind.differ import Diff
from diffmind.reviewer import ReviewResult


def _make_result(label: str, text: str = "review text", error: str = "") -> ReviewResult:
    return ReviewResult(
        diff=Diff(label=label, content="+code", files_changed=["src/foo.py"]),
        text=text,
        model="claude-haiku-4-5-20251001",
        error=error,
    )


class TestFormatMarkdown:
    def test_includes_label(self):
        from diffmind.formatter import format_markdown
        r = _make_result("abc123")
        md = format_markdown([r])
        assert "abc123" in md

    def test_includes_review_text(self):
        from diffmind.formatter import format_markdown
        r = _make_result("x", text="## Summary\nGreat change.")
        md = format_markdown([r])
        assert "Great change" in md

    def test_error_shown(self):
        from diffmind.formatter import format_markdown
        r = _make_result("y", text="", error="API timeout")
        md = format_markdown([r])
        assert "API timeout" in md

    def test_multiple_results(self):
        from diffmind.formatter import format_markdown
        results = [_make_result(f"commit{i}") for i in range(3)]
        md = format_markdown(results)
        for i in range(3):
            assert f"commit{i}" in md


class TestFormatJson:
    def test_valid_json(self):
        from diffmind.formatter import format_json
        r = _make_result("abc")
        data = json.loads(format_json([r]))
        assert isinstance(data, list)
        assert len(data) == 1

    def test_fields_present(self):
        from diffmind.formatter import format_json
        r = _make_result("abc", text="good review")
        data = json.loads(format_json([r]))[0]
        assert data["label"] == "abc"
        assert data["ok"] is True
        assert data["review"] == "good review"
        assert data["model"] == "claude-haiku-4-5-20251001"
        assert "src/foo.py" in data["files_changed"]

    def test_error_result(self):
        from diffmind.formatter import format_json
        r = _make_result("bad", text="", error="timeout")
        data = json.loads(format_json([r]))[0]
        assert data["ok"] is False
        assert data["error"] == "timeout"

    def test_multiple_results(self):
        from diffmind.formatter import format_json
        results = [_make_result(f"r{i}") for i in range(5)]
        data = json.loads(format_json(results))
        assert len(data) == 5
        assert [d["label"] for d in data] == [f"r{i}" for i in range(5)]
