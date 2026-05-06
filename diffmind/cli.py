"""Command-line interface for diffmind."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from . import __version__
from .differ import (
    Diff,
    diff_commit,
    diff_commits,
    diff_head_vs_base,
    diff_staged,
    diff_working,
    read_stdin_diff,
)
from .reviewer import ReviewResult, batch_review, stream_review


# ---------------------------------------------------------------------------
# Rich helpers
# ---------------------------------------------------------------------------

def _console():
    try:
        from rich.console import Console
        return Console()
    except ImportError:
        return None


def _require_rich():
    con = _console()
    if con is None:
        print("pip install rich  # for rich terminal output", file=sys.stderr)
    return con


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_review(args: argparse.Namespace) -> int:
    """Review a single diff (HEAD vs base, staged, working-tree, or stdin)."""
    con = _console()

    async def _get_diff() -> Diff:
        cwd = Path(args.cwd) if args.cwd else None
        if not sys.stdin.isatty() and not args.commits:
            return read_stdin_diff()
        if args.staged:
            return await diff_staged(cwd=cwd)
        if args.working:
            return await diff_working(cwd=cwd)
        if args.commits:
            parts = args.commits
            if len(parts) == 1:
                return await diff_commit(parts[0], cwd=cwd)
            if len(parts) == 2:
                return await diff_commits(parts[0], parts[1], cwd=cwd)
            print("diffmind: --commits takes 1 or 2 refs.", file=sys.stderr)
            sys.exit(2)
        return await diff_head_vs_base(base_branch=args.base, cwd=cwd)

    try:
        diff = asyncio.run(_get_diff())
    except (RuntimeError, ValueError) as exc:
        print(f"diffmind: {exc}", file=sys.stderr)
        return 2

    if diff.is_empty:
        msg = "No changes to review."
        if con:
            con.print(f"[dim]{msg}[/dim]")
        else:
            print(msg)
        return 0

    if args.format in ("table", "rich") and con:
        from rich.markdown import Markdown
        from rich.panel import Panel
        from rich import box as rbox
        from rich.live import Live
        from rich.text import Text

        files = diff.files_changed
        files_note = ""
        if files:
            files_note = f"  [dim]{len(files)} file{'s' if len(files) != 1 else ''}: {', '.join(files[:6])}{'…' if len(files) > 6 else ''}[/dim]"

        con.print()
        con.print(f"[bold cyan]diffmind[/bold cyan]  [dim]{diff.label}[/dim]{files_note}  "
                  f"[dim]model={args.model} focus={args.focus}[/dim]")
        con.print()

        collected: list[str] = []

        with Live(console=con, refresh_per_second=12) as live:
            def on_chunk(text: str) -> None:
                collected.append(text)
                md = Markdown("".join(collected))
                live.update(Panel(md, border_style="cyan", box=rbox.ROUNDED))

            try:
                result = stream_review(
                    diff,
                    model=args.model,
                    focus=args.focus,
                    on_chunk=on_chunk,
                )
            except (ImportError, EnvironmentError) as exc:
                con.print(f"[red]{exc}[/red]")
                return 1

        if result.truncated:
            con.print("[yellow]⚠ Diff was truncated to fit the context window.[/yellow]")
        return 0 if result.ok else 1

    # Plain / markdown / json path
    collected: list[str] = []

    def on_chunk_plain(text: str) -> None:
        collected.append(text)
        if args.format not in ("json",):
            print(text, end="", flush=True)

    try:
        result = stream_review(diff, model=args.model, focus=args.focus, on_chunk=on_chunk_plain)
    except (ImportError, EnvironmentError) as exc:
        print(f"diffmind: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        from .formatter import format_json
        print(format_json([result]))
    elif args.format == "markdown" and args.format != "rich":
        pass  # already printed via on_chunk_plain

    if result.truncated:
        print("\n⚠ Diff was truncated to fit the context window.", file=sys.stderr)

    return 0 if result.ok else 1


def cmd_batch(args: argparse.Namespace) -> int:
    """Review multiple commits concurrently using asyncio.TaskGroup."""
    con = _console()
    cwd = Path(args.cwd) if args.cwd else None

    async def _run() -> list[ReviewResult]:
        async def _load(ref: str) -> Diff:
            return await diff_commit(ref, cwd=cwd)

        diffs: list[Diff] = []
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_load(ref)) for ref in args.refs]
        diffs = [t.result() for t in tasks]

        finished: list[ReviewResult] = []

        def _on_result(r: ReviewResult) -> None:
            finished.append(r)
            if con:
                from .formatter import format_rich
                format_rich(r, con)
            else:
                print(f"\n=== {r.diff.label} ===\n")
                if r.error:
                    print(f"ERROR: {r.error}")
                else:
                    print(r.text)

        return await batch_review(
            diffs,
            model=args.model,
            focus=args.focus,
            on_result=_on_result,
            max_concurrent=args.concurrency,
        )

    if con:
        con.print(
            f"[bold cyan]diffmind batch[/bold cyan]  "
            f"[dim]{len(args.refs)} commits · model={args.model} · "
            f"concurrency={args.concurrency}[/dim]"
        )

    try:
        results = asyncio.run(_run())
    except* RuntimeError as eg:
        for exc in eg.exceptions:
            print(f"diffmind: {exc}", file=sys.stderr)
        return 1
    except (ImportError, EnvironmentError) as exc:
        print(f"diffmind: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        from .formatter import format_json
        print(format_json(results))
    elif args.format == "markdown":
        from .formatter import format_markdown
        print(format_markdown(results))

    errors = [r for r in results if not r.ok]
    if errors:
        print(f"\n{len(errors)} review(s) failed.", file=sys.stderr)
        return 1
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    """Review the last N commits on the current branch one by one."""
    con = _console()
    cwd = Path(args.cwd) if args.cwd else None

    async def _get_refs() -> list[str]:
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            "git", "log", f"-{args.n}", "--format=%H",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode().strip())
        return [h.strip() for h in stdout.decode().splitlines() if h.strip()]

    try:
        refs = asyncio.run(_get_refs())
    except RuntimeError as exc:
        print(f"diffmind: {exc}", file=sys.stderr)
        return 2

    if not refs:
        print("No commits found.")
        return 0

    # Reuse batch logic by setting args.refs
    args.refs = refs
    return cmd_batch(args)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="diffmind",
        description="AI-powered git diff reviewer — streaming analysis, concurrent batch mode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  diffmind review                          # review current branch vs main
  diffmind review --base develop           # review vs develop branch
  diffmind review --staged                 # review staged changes
  diffmind review --working                # review unstaged changes
  diffmind review --commits abc123         # review a single commit
  diffmind review --commits main HEAD      # review main..HEAD
  git diff | diffmind review               # pipe a diff directly
  diffmind review --format json            # machine-readable output
  diffmind review --focus issues           # only flag bugs/security issues
  diffmind review --model claude-sonnet-4-6  # deeper analysis

  diffmind batch abc123 def456 ghi789      # review 3 commits concurrently
  diffmind log --n 5                       # review last 5 commits
  diffmind log --n 10 --format markdown    # export as markdown
""",
    )
    p.add_argument("--version", action="version", version=f"diffmind {__version__}")
    p.add_argument("--cwd", metavar="DIR", help="Git repository directory (default: current dir)")

    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    # -- review --
    pr = sub.add_parser("review", help="Review a single diff with streaming AI analysis")
    pr.add_argument(
        "--base", default="main", metavar="BRANCH",
        help="Base branch to diff against (default: main)",
    )
    pr.add_argument(
        "--staged", action="store_true",
        help="Review staged (indexed) changes",
    )
    pr.add_argument(
        "--working", action="store_true",
        help="Review unstaged working-tree changes",
    )
    pr.add_argument(
        "--commits", nargs="+", metavar="REF",
        help="Review a single commit (1 arg) or commit range (2 args: BASE HEAD)",
    )
    pr.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
        metavar="MODEL",
        help="Claude model ID (default: claude-haiku-4-5-20251001)",
    )
    pr.add_argument(
        "--focus", choices=["full", "summary", "issues", "suggest"], default="full",
        help="Review focus (default: full)",
    )
    pr.add_argument(
        "--format", "-f", choices=["rich", "markdown", "json"], default="rich",
        help="Output format (default: rich)",
    )
    pr.set_defaults(func=cmd_review)

    # -- batch --
    pb = sub.add_parser("batch", help="Review multiple commits concurrently (asyncio.TaskGroup)")
    pb.add_argument("refs", nargs="+", metavar="COMMIT", help="Commit SHAs or refs to review")
    pb.add_argument("--model", default="claude-haiku-4-5-20251001", metavar="MODEL")
    pb.add_argument(
        "--focus", choices=["full", "summary", "issues", "suggest"], default="summary",
        help="Review focus (default: summary for batch)",
    )
    pb.add_argument(
        "--concurrency", "-c", type=int, default=4, metavar="N",
        help="Max concurrent reviews (default: 4)",
    )
    pb.add_argument(
        "--format", "-f", choices=["rich", "markdown", "json"], default="rich",
        help="Output format (default: rich)",
    )
    pb.set_defaults(func=cmd_batch)

    # -- log --
    pl = sub.add_parser("log", help="Review the last N commits on the current branch")
    pl.add_argument("--n", type=int, default=5, metavar="N", help="Number of commits (default: 5)")
    pl.add_argument("--model", default="claude-haiku-4-5-20251001", metavar="MODEL")
    pl.add_argument(
        "--focus", choices=["full", "summary", "issues", "suggest"], default="summary",
    )
    pl.add_argument(
        "--concurrency", "-c", type=int, default=4, metavar="N",
    )
    pl.add_argument(
        "--format", "-f", choices=["rich", "markdown", "json"], default="rich",
    )
    pl.set_defaults(func=cmd_log)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


def entry_point() -> None:
    sys.exit(main())
