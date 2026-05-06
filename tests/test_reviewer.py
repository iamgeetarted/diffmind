"""Tests for the reviewer module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from diffmind.differ import Diff
from diffmind.reviewer import ReviewResult, _build_prompt, _MAX_DIFF_CHARS


class TestBuildPrompt:
    def test_includes_label(self):
        d = Diff(label="abc123..def456", content="+ new line")
        prompt = _build_prompt(d, "full")
        assert "abc123..def456" in prompt

    def test_truncates_large_diffs(self):
        huge = "+" + "x" * (_MAX_DIFF_CHARS + 100)
        d = Diff(label="big", content=huge)
        prompt = _build_prompt(d, "full")
        assert "truncated" in prompt

    def test_includes_files(self):
        d = Diff(label="x", content="+ y", files_changed=["src/auth.py", "tests/test_auth.py"])
        prompt = _build_prompt(d, "full")
        assert "src/auth.py" in prompt

    def test_focus_summary(self):
        d = Diff(label="x", content="+ y")
        prompt = _build_prompt(d, "summary")
        assert "3-5 sentences" in prompt

    def test_focus_issues(self):
        d = Diff(label="x", content="+ y")
        prompt = _build_prompt(d, "issues")
        assert "security" in prompt.lower()

    def test_focus_suggest(self):
        d = Diff(label="x", content="+ y")
        prompt = _build_prompt(d, "suggest")
        assert "suggestion" in prompt.lower()


class TestReviewResult:
    def test_ok_true(self):
        r = ReviewResult(diff=Diff("x", "y"), text="ok", model="haiku")
        assert r.ok

    def test_ok_false_when_error(self):
        r = ReviewResult(diff=Diff("x", "y"), text="", model="haiku", error="oops")
        assert not r.ok


class TestStreamReview:
    def test_empty_diff_returns_early(self):
        from diffmind.reviewer import stream_review
        d = Diff(label="empty", content="  ")
        r = stream_review(d, api_key="fake")
        assert "(empty diff" in r.text
        assert r.ok

    def test_streams_chunks(self):
        from diffmind.reviewer import stream_review

        mock_client = MagicMock()
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.text_stream = iter(["chunk1", " chunk2"])
        mock_client.messages.stream.return_value = mock_stream

        received: list[str] = []
        with patch("diffmind.reviewer._get_client", return_value=mock_client):
            result = stream_review(
                Diff(label="test", content="+code"),
                on_chunk=received.append,
            )

        assert result.text == "chunk1 chunk2"
        assert received == ["chunk1", " chunk2"]
        assert result.ok

    def test_truncation_flag(self):
        from diffmind.reviewer import stream_review

        long_content = "+" + "x" * (_MAX_DIFF_CHARS + 50)
        d = Diff(label="large", content=long_content)

        mock_client = MagicMock()
        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.text_stream = iter(["review text"])
        mock_client.messages.stream.return_value = mock_stream

        with patch("diffmind.reviewer._get_client", return_value=mock_client):
            result = stream_review(d)

        assert result.truncated


class TestBatchReview:
    def test_batch_returns_ordered_results(self):
        import asyncio
        from diffmind.reviewer import batch_review

        diffs = [
            Diff(label="d1", content="  "),   # empty
            Diff(label="d2", content="  "),   # empty
            Diff(label="d3", content="  "),   # empty
        ]

        results = asyncio.run(batch_review(diffs, api_key="fake"))
        assert len(results) == 3
        assert [r.diff.label for r in results] == ["d1", "d2", "d3"]

    def test_on_result_callback(self):
        import asyncio
        from diffmind.reviewer import batch_review

        diffs = [Diff(label="x", content="  ")]
        called: list[ReviewResult] = []
        asyncio.run(batch_review(diffs, api_key="fake", on_result=called.append))
        assert len(called) == 1
