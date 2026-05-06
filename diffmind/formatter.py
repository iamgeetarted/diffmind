"""Output formatters for review results."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .reviewer import ReviewResult


def format_rich(result: "ReviewResult", console) -> None:
    """Render a ReviewResult to a Rich console with panels and markdown."""
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich import box as rbox

    status = "[red]✗ Error[/red]" if result.error else "[green]✓ Done[/green]"
    trunc = "  [yellow][truncated][/yellow]" if result.truncated else ""
    files = ""
    if result.diff.files_changed:
        fc = result.diff.files_changed
        files = f"  [dim]{len(fc)} file{'s' if len(fc) != 1 else ''}: {', '.join(fc[:5])}{'…' if len(fc) > 5 else ''}[/dim]"

    title = f"{status}  [bold]{result.diff.label}[/bold]{trunc}{files}"

    if result.error:
        console.print(Panel(f"[red]{result.error}[/red]", title=title, border_style="red", box=rbox.ROUNDED))
    else:
        md = Markdown(result.text)
        console.print(Panel(md, title=title, border_style="cyan", box=rbox.ROUNDED))


def format_markdown(results: list["ReviewResult"]) -> str:
    """Return all results as a single Markdown document."""
    lines = ["# diffmind Review\n"]
    for r in results:
        lines.append(f"## {r.diff.label}\n")
        if r.diff.files_changed:
            lines.append(f"*Files: {', '.join(r.diff.files_changed)}*\n")
        if r.error:
            lines.append(f"> **Error:** {r.error}\n")
        else:
            lines.append(r.text)
        lines.append("\n---\n")
    return "\n".join(lines)


def format_json(results: list["ReviewResult"]) -> str:
    """Return all results serialised as JSON."""
    output = []
    for r in results:
        output.append({
            "label": r.diff.label,
            "model": r.model,
            "ok": r.ok,
            "truncated": r.truncated,
            "files_changed": r.diff.files_changed,
            "error": r.error,
            "review": r.text,
        })
    return json.dumps(output, indent=2)
