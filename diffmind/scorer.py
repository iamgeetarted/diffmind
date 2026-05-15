"""Complexity and risk scoring for diffs — no AI required."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .differ import Diff


@dataclass
class DiffScore:
    """Risk and complexity metrics for a single diff."""

    label: str
    lines_added: int
    lines_removed: int
    net_change: int
    churn: int
    files_changed: int
    source_files: int
    test_files: int
    config_files: int
    migration_files: int
    other_files: int
    test_coverage_ratio: float
    risk_score: int
    risk_level: str
    risk_color: str
    complexity_notes: list[str] = field(default_factory=list)


def _categorise_files(files: list[str]) -> tuple[int, int, int, int]:
    """Return (source_files, test_files, config_files, migration_files)."""
    _CONFIG_SUFFIXES = {".toml", ".yaml", ".yml", ".json", ".cfg", ".ini", ".env"}
    _CONFIG_NAMES = {"Dockerfile"}
    _CONFIG_PATTERNS = {".github"}

    source = 0
    test = 0
    config = 0
    migration = 0

    for path in files:
        lower = path.lower()
        # Check test/spec
        if "test" in lower or "spec" in lower:
            test += 1
            continue
        # Check migration/alembic
        if "migration" in lower or "alembic" in lower:
            migration += 1
            continue
        # Check config/infra
        from pathlib import PurePosixPath
        p = PurePosixPath(path)
        suffix = p.suffix
        name = p.name
        if (
            suffix in _CONFIG_SUFFIXES
            or name in _CONFIG_NAMES
            or any(pat in path for pat in _CONFIG_PATTERNS)
        ):
            config += 1
            continue
        # Everything else is source
        source += 1

    return source, test, config, migration


def score_diff(diff: "Diff") -> DiffScore:
    """Compute a DiffScore for the given Diff."""
    lines_added = 0
    lines_removed = 0

    for line in diff.content.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines_added += 1
        elif line.startswith("-") and not line.startswith("---"):
            lines_removed += 1

    net_change = lines_added - lines_removed
    churn = lines_added + lines_removed

    source_files, test_files, config_files, migration_files = _categorise_files(
        diff.files_changed
    )
    other_files = source_files  # alias used in cli.py display
    files_changed = len(diff.files_changed)

    test_coverage_ratio = test_files / max(source_files, 1)

    # Risk score computation
    risk = 0.0
    risk += min(churn / 10, 40)  # up to 40 for churn
    if migration_files > 0:
        risk += 20
    if config_files > 0:
        risk += 15
    if test_files == 0 and source_files > 0:
        risk += 10
    if test_coverage_ratio > 0.3:
        risk -= 10

    risk_score = int(max(0, min(100, risk)))

    if risk_score <= 25:
        risk_level = "low"
        risk_color = "green"
    elif risk_score <= 50:
        risk_level = "medium"
        risk_color = "yellow"
    elif risk_score <= 75:
        risk_level = "high"
        risk_color = "red"
    else:
        risk_level = "critical"
        risk_color = "bold red"

    # Complexity notes
    notes: list[str] = []

    if churn == 0:
        notes.append("Empty diff — no lines changed")
    elif churn < 50:
        notes.append(f"Small change: {churn} lines changed")
    elif churn < 200:
        notes.append(f"Moderate churn: {churn} lines changed")
    else:
        notes.append(f"Large churn: {churn} lines changed")

    if migration_files > 0:
        notes.append("Touches migration files")

    if config_files > 0:
        cfg_names = [
            f for f in diff.files_changed
            if not ("test" in f.lower() or "spec" in f.lower() or "migration" in f.lower() or "alembic" in f.lower())
            and _is_config_file(f)
        ]
        if cfg_names:
            notes.append(f"Touches config/infra files: {', '.join(cfg_names[:3])}")
        else:
            notes.append("Touches config/infra files")

    if test_files == 0 and source_files > 0:
        notes.append("No tests changed alongside source changes")

    if test_coverage_ratio > 0.3:
        notes.append(f"Good test coverage ratio: {test_coverage_ratio:.0%} tests vs source")

    return DiffScore(
        label=diff.label,
        lines_added=lines_added,
        lines_removed=lines_removed,
        net_change=net_change,
        churn=churn,
        files_changed=files_changed,
        source_files=source_files,
        test_files=test_files,
        config_files=config_files,
        migration_files=migration_files,
        other_files=other_files,
        test_coverage_ratio=test_coverage_ratio,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_color=risk_color,
        complexity_notes=notes,
    )


def _is_config_file(path: str) -> bool:
    """Return True if the path looks like a config/infra file."""
    _CONFIG_SUFFIXES = {".toml", ".yaml", ".yml", ".json", ".cfg", ".ini", ".env"}
    _CONFIG_NAMES = {"Dockerfile"}
    _CONFIG_PATTERNS = {".github"}
    from pathlib import PurePosixPath
    p = PurePosixPath(path)
    return (
        p.suffix in _CONFIG_SUFFIXES
        or p.name in _CONFIG_NAMES
        or any(pat in path for pat in _CONFIG_PATTERNS)
    )
