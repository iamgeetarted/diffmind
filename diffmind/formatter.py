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


def _md_to_html(text: str) -> str:
    """Convert a subset of Markdown to HTML using simple regex replacements."""
    import re
    import html as html_lib

    lines = text.split("\n")
    html_lines: list[str] = []
    in_ul = False

    for line in lines:
        # Escape HTML entities first (before adding our own tags)
        # We'll process raw line and handle markup
        is_bullet = re.match(r"^[-*]\s+(.+)$", line)
        is_h2 = re.match(r"^##\s+(.+)$", line)
        is_h3 = re.match(r"^###\s+(.+)$", line)

        if is_bullet:
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            content = html_lib.escape(is_bullet.group(1))
            # inline: **bold**, `code`
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            content = re.sub(r"`(.+?)`", r"<code>\1</code>", content)
            html_lines.append(f"  <li>{content}</li>")
        else:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if is_h2:
                content = html_lib.escape(is_h2.group(1))
                html_lines.append(f"<h2>{content}</h2>")
            elif is_h3:
                content = html_lib.escape(is_h3.group(1))
                html_lines.append(f"<h3>{content}</h3>")
            elif line.strip() == "":
                html_lines.append("<br>")
            else:
                content = html_lib.escape(line)
                content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                content = re.sub(r"`(.+?)`", r"<code>\1</code>", content)
                html_lines.append(f"<p>{content}</p>")

    if in_ul:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def format_html(results: list["ReviewResult"]) -> str:
    """Return a self-contained, dark-themed HTML report for all results."""
    import html as html_lib

    css = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        background: #1e1e1e;
        color: #d4d4d4;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
        font-size: 15px;
        line-height: 1.6;
        padding: 2rem;
    }
    h1 {
        color: #4ec9b0;
        font-size: 1.8rem;
        margin-bottom: 0.5rem;
    }
    .meta {
        color: #858585;
        font-size: 0.85rem;
        margin-bottom: 2rem;
    }
    section.card {
        background: #252526;
        border: 1px solid #3c3c3c;
        border-radius: 8px;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
    }
    .card-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 1rem;
        border-bottom: 1px solid #3c3c3c;
        padding-bottom: 0.75rem;
    }
    .card-header h2 {
        font-size: 1.1rem;
        color: #9cdcfe;
        flex: 1;
    }
    .status-ok   { color: #4ec9b0; font-weight: bold; }
    .status-err  { color: #f44747; font-weight: bold; }
    .files-list {
        font-size: 0.8rem;
        color: #858585;
        margin-bottom: 1rem;
        font-family: monospace;
    }
    .files-list span {
        background: #2d2d30;
        border-radius: 3px;
        padding: 1px 5px;
        margin-right: 4px;
        display: inline-block;
        margin-bottom: 3px;
    }
    .review-body h2 {
        color: #ce9178;
        font-size: 1rem;
        margin: 1rem 0 0.4rem;
    }
    .review-body h3 {
        color: #dcdcaa;
        font-size: 0.95rem;
        margin: 0.8rem 0 0.3rem;
    }
    .review-body p {
        margin-bottom: 0.5rem;
    }
    .review-body ul {
        margin: 0.3rem 0 0.6rem 1.4rem;
    }
    .review-body li {
        margin-bottom: 0.2rem;
    }
    .review-body code {
        background: #2d2d30;
        color: #ce9178;
        border-radius: 3px;
        padding: 1px 4px;
        font-family: monospace;
        font-size: 0.9em;
    }
    .review-body strong {
        color: #ffffff;
    }
    .truncated-warning {
        color: #ddb100;
        font-size: 0.85rem;
        margin-top: 0.75rem;
    }
    .error-body {
        color: #f44747;
        font-family: monospace;
        font-size: 0.9rem;
    }
    """

    sections: list[str] = []
    for r in results:
        label_escaped = html_lib.escape(r.diff.label)
        status_html = (
            '<span class="status-err">&#x2717; Error</span>'
            if r.error
            else '<span class="status-ok">&#x2713; Done</span>'
        )

        files_html = ""
        if r.diff.files_changed:
            file_spans = "".join(
                f"<span>{html_lib.escape(f)}</span>"
                for f in r.diff.files_changed[:10]
            )
            if len(r.diff.files_changed) > 10:
                file_spans += f"<span>+{len(r.diff.files_changed) - 10} more</span>"
            files_html = f'<div class="files-list">{file_spans}</div>'

        if r.error:
            body_html = f'<div class="error-body">{html_lib.escape(r.error)}</div>'
        else:
            body_html = f'<div class="review-body">{_md_to_html(r.text)}</div>'

        trunc_html = ""
        if r.truncated:
            trunc_html = '<p class="truncated-warning">&#9888; Diff was truncated to fit the context window.</p>'

        model_note = html_lib.escape(r.model)

        section = f"""
  <section class="card">
    <div class="card-header">
      {status_html}
      <h2>{label_escaped}</h2>
      <span style="color:#858585;font-size:0.8rem">{model_note}</span>
    </div>
    {files_html}
    {body_html}
    {trunc_html}
  </section>"""
        sections.append(section)

    sections_html = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>diffmind review report</title>
  <style>{css}
  </style>
</head>
<body>
  <h1>diffmind</h1>
  <p class="meta">Generated by diffmind &mdash; AI-powered git diff reviewer</p>
{sections_html}
</body>
</html>
"""
