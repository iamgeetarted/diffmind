"""Extract git diffs from the repository or stdin."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Diff:
    """A single diff payload ready for review."""

    label: str
    content: str
    base: str = ""
    head: str = ""
    files_changed: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.content.strip()

    @property
    def line_count(self) -> int:
        return self.content.count("\n")


async def _run_git(*args: str, cwd: Path | None = None) -> str:
    """Run a git command asynchronously and return stdout."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise RuntimeError(f"git {' '.join(args)}: {err}")
    return stdout.decode()


async def diff_commits(base: str, head: str, cwd: Path | None = None) -> Diff:
    """Return the diff between two git refs."""
    content = await _run_git("diff", base, head, cwd=cwd)
    files_raw = await _run_git("diff", "--name-only", base, head, cwd=cwd)
    files = [f for f in files_raw.splitlines() if f.strip()]
    label = f"{base}..{head}"
    return Diff(label=label, content=content, base=base, head=head, files_changed=files)


async def diff_staged(cwd: Path | None = None) -> Diff:
    """Return the currently staged diff."""
    content = await _run_git("diff", "--cached", cwd=cwd)
    files_raw = await _run_git("diff", "--cached", "--name-only", cwd=cwd)
    files = [f for f in files_raw.splitlines() if f.strip()]
    return Diff(label="staged", content=content, files_changed=files)


async def diff_working(cwd: Path | None = None) -> Diff:
    """Return the unstaged working-tree diff."""
    content = await _run_git("diff", cwd=cwd)
    files_raw = await _run_git("diff", "--name-only", cwd=cwd)
    files = [f for f in files_raw.splitlines() if f.strip()]
    return Diff(label="working", content=content, files_changed=files)


async def diff_commit(commit: str, cwd: Path | None = None) -> Diff:
    """Return the diff introduced by a single commit."""
    content = await _run_git("show", "--format=", commit, cwd=cwd)
    files_raw = await _run_git("show", "--name-only", "--format=", commit, cwd=cwd)
    files = [f for f in files_raw.splitlines() if f.strip()]
    try:
        subject_raw = await _run_git("log", "-1", "--format=%s", commit, cwd=cwd)
        subject = subject_raw.strip()
    except RuntimeError:
        subject = commit
    label = f"{commit[:8]}: {subject}"
    return Diff(label=label, content=content, head=commit, files_changed=files)


async def diff_head_vs_base(base_branch: str = "main", cwd: Path | None = None) -> Diff:
    """Return the diff of the current branch against a base branch."""
    try:
        merge_base = await _run_git("merge-base", "HEAD", base_branch, cwd=cwd)
        merge_base = merge_base.strip()
    except RuntimeError:
        merge_base = base_branch
    return await diff_commits(merge_base, "HEAD", cwd=cwd)


def read_stdin_diff() -> Diff:
    """Read a diff from stdin."""
    if sys.stdin.isatty():
        raise ValueError("No diff on stdin and no arguments given. Pipe a diff or pass --commits.")
    content = sys.stdin.read()
    return Diff(label="stdin", content=content)
