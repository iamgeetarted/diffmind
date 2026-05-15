"""Append-only JSONL review history stored at ~/.diffmind/history.jsonl."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from .reviewer import ReviewResult


def save_review(result: "ReviewResult", path: Path | None = None) -> None:
    """Append a ReviewResult to the JSONL history file."""
    if path is None:
        path = Path.home() / ".diffmind" / "history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "label": result.diff.label,
        "model": result.model,
        "focus": "",  # filled in by caller if known
        "lines": result.diff.line_count,
        "files": result.diff.files_changed,
        "truncated": result.truncated,
        "error": result.error,
        "review": result.text,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def iter_history(path: Path, limit: int = 200) -> Iterator[dict]:
    """Yield history entries newest-first."""
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if line:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                pass


def history_stats(path: Path) -> dict:
    """Return summary stats dict: count, newest, oldest, models, path."""
    from collections import Counter
    entries = list(iter_history(path, limit=10000))
    if not entries:
        return {"count": 0, "newest": "", "oldest": "", "models": {}, "path": str(path)}
    models: Counter[str] = Counter(e.get("model", "?") for e in entries)
    timestamps = [e.get("ts", "") for e in entries if e.get("ts")]
    return {
        "count": len(entries),
        "newest": max(timestamps, default="")[:19].replace("T", " "),
        "oldest": min(timestamps, default="")[:19].replace("T", " "),
        "models": dict(models),
        "path": str(path),
    }
