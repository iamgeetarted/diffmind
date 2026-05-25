"""Fetch a GitHub Pull Request diff for review."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .differ import Diff


def _parse_pr_url(ref: str) -> tuple[str, str, str]:
    """Parse 'owner/repo#N', 'owner/repo/pull/N', or full GitHub URL into (owner, repo, number)."""
    # Full URL: https://github.com/owner/repo/pull/123
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)",
        ref,
    )
    if m:
        return m.group(1), m.group(2), m.group(3)

    # Short form owner/repo#N
    m = re.match(r"([^/]+)/([^#]+)#(\d+)$", ref)
    if m:
        return m.group(1), m.group(2), m.group(3)

    # owner/repo/pull/N (no host)
    m = re.match(r"([^/]+)/([^/]+)/pull/(\d+)$", ref)
    if m:
        return m.group(1), m.group(2), m.group(3)

    raise ValueError(
        f"Cannot parse PR reference '{ref}'. "
        "Use 'owner/repo#N', 'owner/repo/pull/N', or a full GitHub URL."
    )


def fetch_pr_diff(ref: str, token: str | None = None) -> "Diff":
    """Fetch the unified diff for a GitHub PR.

    *token* defaults to $GITHUB_TOKEN.  Without a token the request still
    works for public repos but is rate-limited to 60 req/h.
    """
    import urllib.request

    from .differ import Diff

    owner, repo, number = _parse_pr_url(ref)
    token = token or os.environ.get("GITHUB_TOKEN", "")

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3.diff")
    req.add_header("User-Agent", "diffmind/1.3")
    if token:
        req.add_header("Authorization", f"token {token}")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            diff_text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"GitHub API error: {exc}") from exc

    # Pull PR metadata for the label
    meta_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    meta_req = urllib.request.Request(meta_url)
    meta_req.add_header("Accept", "application/vnd.github.v3+json")
    meta_req.add_header("User-Agent", "diffmind/1.3")
    if token:
        meta_req.add_header("Authorization", f"token {token}")

    title = f"{owner}/{repo}#PR{number}"
    try:
        import json
        with urllib.request.urlopen(meta_req, timeout=10) as resp:
            meta = json.loads(resp.read())
            pr_title = meta.get("title", "")
            if pr_title:
                title = f"PR#{number}: {pr_title}"
    except Exception:
        pass

    # Extract changed files from diff headers
    files = re.findall(r"^diff --git a/(.+?) b/", diff_text, re.MULTILINE)

    return Diff(
        label=title,
        content=diff_text,
        files_changed=files,
    )
