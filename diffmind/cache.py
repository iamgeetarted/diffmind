"""Disk-based review cache keyed by diff content hash, with TTL expiry."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .reviewer import ReviewResult

_DEFAULT_TTL = 7 * 24 * 3600  # 7 days
_CACHE_DIR = Path.home() / ".diffmind" / "cache"


def _cache_key(content: str, model: str, focus: str) -> str:
    raw = f"{model}:{focus}:{content}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def get_cached(content: str, model: str, focus: str, ttl: int = _DEFAULT_TTL) -> dict | None:
    """Return cached entry if it exists and has not expired, else None."""
    key = _cache_key(content, model, focus)
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - entry.get("ts", 0) > ttl:
            path.unlink(missing_ok=True)
            return None
        return entry
    except Exception:
        return None


def put_cached(content: str, model: str, focus: str, review_text: str, truncated: bool) -> None:
    """Write a review result to the cache."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(content, model, focus)
    path = _cache_path(key)
    entry = {
        "ts": time.time(),
        "model": model,
        "focus": focus,
        "review": review_text,
        "truncated": truncated,
    }
    path.write_text(json.dumps(entry), encoding="utf-8")


def cache_stats() -> dict:
    """Return stats: entry count, total size, oldest/newest timestamps."""
    if not _CACHE_DIR.exists():
        return {"count": 0, "size_bytes": 0, "oldest": None, "newest": None, "path": str(_CACHE_DIR)}
    files = list(_CACHE_DIR.glob("*.json"))
    if not files:
        return {"count": 0, "size_bytes": 0, "oldest": None, "newest": None, "path": str(_CACHE_DIR)}
    timestamps: list[float] = []
    total_size = 0
    for f in files:
        total_size += f.stat().st_size
        try:
            entry = json.loads(f.read_text())
            timestamps.append(entry.get("ts", 0))
        except Exception:
            pass
    return {
        "count": len(files),
        "size_bytes": total_size,
        "oldest": min(timestamps) if timestamps else None,
        "newest": max(timestamps) if timestamps else None,
        "path": str(_CACHE_DIR),
    }


def cache_clear() -> int:
    """Delete all cache entries; returns count removed."""
    if not _CACHE_DIR.exists():
        return 0
    files = list(_CACHE_DIR.glob("*.json"))
    for f in files:
        f.unlink(missing_ok=True)
    return len(files)
