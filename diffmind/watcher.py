"""Watch mode: poll the git log and auto-review each new commit as it lands."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable


async def _latest_commits(n: int = 20, cwd: Path | None = None) -> list[str]:
    """Return the most recent *n* commit SHAs."""
    proc = await asyncio.create_subprocess_exec(
        "git", "log", f"-{n}", "--format=%H",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, _ = await proc.communicate()
    return [h.strip() for h in stdout.decode().splitlines() if h.strip()]


async def watch(
    *,
    cwd: Path | None = None,
    model: str = "claude-haiku-4-5-20251001",
    focus: str = "summary",
    poll_interval: float = 5.0,
    on_new_commit: Callable[[str], None] | None = None,
) -> None:
    """Poll the git log every *poll_interval* seconds and review new commits.

    Calls *on_new_commit(sha)* for each new commit before reviewing so callers
    can update a live display.  Press Ctrl-C to stop.
    """
    from .differ import diff_commit
    from .reviewer import stream_review

    seen: set[str] = set(await _latest_commits(50, cwd=cwd))

    while True:
        await asyncio.sleep(poll_interval)
        current = await _latest_commits(20, cwd=cwd)
        new = [sha for sha in current if sha not in seen]
        for sha in reversed(new):  # oldest-first
            seen.add(sha)
            if on_new_commit:
                on_new_commit(sha)
            try:
                diff = await diff_commit(sha, cwd=cwd)
                stream_review(diff, model=model, focus=focus)
            except Exception:
                pass
