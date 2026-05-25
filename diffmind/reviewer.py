"""Core review logic: send diffs to Claude and stream structured analysis."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from .differ import Diff

_MAX_DIFF_CHARS = 24_000  # keep prompts within token budget


@dataclass
class ReviewResult:
    """Completed review for one diff."""

    diff: Diff
    text: str
    model: str
    truncated: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def _get_client(api_key: str | None = None):
    """Return an anthropic.Anthropic client."""
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError("pip install anthropic  # required for AI review") from exc
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Export it:  export ANTHROPIC_API_KEY=your-key"
        )
    return anthropic.Anthropic(api_key=key)


def _build_prompt(diff: Diff, focus: str) -> str:
    content = diff.content
    truncated = len(content) > _MAX_DIFF_CHARS
    if truncated:
        content = content[:_MAX_DIFF_CHARS] + "\n\n[... diff truncated ...]"

    files_note = ""
    if diff.files_changed:
        files_note = f"Files changed: {', '.join(diff.files_changed[:20])}\n"

    focus_map = {
        "full": (
            "Provide a structured code review with these sections:\n"
            "## Summary\nWhat changed and why (2-3 sentences).\n\n"
            "## Key Changes\nBullet list of the most important changes.\n\n"
            "## Potential Issues\nBugs, security concerns, or logic errors (if any; skip if none).\n\n"
            "## Suggestions\n1-3 actionable improvements (if any; skip if none).\n\n"
            "## Verdict\nOne line: LGTM / Needs work / Needs discussion."
        ),
        "summary": "Summarize this diff in 3-5 sentences. Focus on what changed and why.",
        "issues": (
            "List only the potential bugs, security concerns, and logic errors in this diff. "
            "Be specific about file and line. If none, say 'No issues found.'"
        ),
        "suggest": (
            "List 3-5 concrete, actionable improvement suggestions for this diff. "
            "Be specific and reference the actual code."
        ),
    }
    instructions = focus_map.get(focus, focus_map["full"])

    return (
        f"You are an expert code reviewer. Review this git diff:\n\n"
        f"{files_note}"
        f"Label: {diff.label}\n\n"
        f"```diff\n{content}\n```\n\n"
        f"{instructions}\n\n"
        "Be concise, specific, and use markdown formatting."
    )


def stream_review(
    diff: Diff,
    model: str = "claude-haiku-4-5-20251001",
    focus: str = "full",
    api_key: str | None = None,
    on_chunk: Callable[[str], None] | None = None,
    use_cache: bool = True,
    cache_ttl: int = 7 * 24 * 3600,
) -> ReviewResult:
    """Stream a review for *diff*, calling *on_chunk* for each text chunk.

    Caches results to ~/.diffmind/cache/ by diff content hash (use_cache=True by default).
    Returns the completed ReviewResult when streaming ends.
    """
    if diff.is_empty:
        return ReviewResult(diff=diff, text="(empty diff — nothing to review)", model=model)

    truncated = len(diff.content) > _MAX_DIFF_CHARS

    if use_cache:
        from .cache import get_cached, put_cached
        cached = get_cached(diff.content, model, focus, ttl=cache_ttl)
        if cached:
            text = cached["review"]
            if on_chunk:
                on_chunk(text)
            return ReviewResult(
                diff=diff,
                text=text,
                model=model,
                truncated=cached.get("truncated", truncated),
                error="",
            )

    client = _get_client(api_key)
    prompt = _build_prompt(diff, focus)

    chunks: list[str] = []
    with client.messages.stream(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            chunks.append(chunk)
            if on_chunk:
                on_chunk(chunk)

    text = "".join(chunks)
    if use_cache:
        from .cache import put_cached
        put_cached(diff.content, model, focus, text, truncated)

    return ReviewResult(
        diff=diff,
        text=text,
        model=model,
        truncated=truncated,
    )


async def stream_review_async(
    diff: Diff,
    model: str = "claude-haiku-4-5-20251001",
    focus: str = "full",
    api_key: str | None = None,
    on_chunk: Callable[[str], None] | None = None,
) -> ReviewResult:
    """Async wrapper around stream_review for use in TaskGroup."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: stream_review(diff, model=model, focus=focus, api_key=api_key, on_chunk=on_chunk),
    )


async def batch_review(
    diffs: list[Diff],
    model: str = "claude-haiku-4-5-20251001",
    focus: str = "full",
    api_key: str | None = None,
    on_result: Callable[[ReviewResult], None] | None = None,
    max_concurrent: int = 4,
) -> list[ReviewResult]:
    """Review multiple diffs concurrently using asyncio.TaskGroup.

    Results are returned in the same order as *diffs*.
    *on_result* is called as each review completes (out of order).
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[ReviewResult | None] = [None] * len(diffs)
    errors: list[str] = []

    async def _review_one(idx: int, diff: Diff) -> None:
        async with semaphore:
            try:
                result = await stream_review_async(diff, model=model, focus=focus, api_key=api_key)
            except Exception as exc:
                result = ReviewResult(diff=diff, text="", model=model, error=str(exc))
            results[idx] = result
            if on_result:
                on_result(result)

    async with asyncio.TaskGroup() as tg:
        for i, diff in enumerate(diffs):
            tg.create_task(_review_one(i, diff))

    return [r for r in results if r is not None]
