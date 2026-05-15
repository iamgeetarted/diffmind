"""Load persistent settings from ~/.diffmind.toml."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

_CONFIG_PATH = Path.home() / ".diffmind.toml"

@dataclass
class DiffmindConfig:
    default_model: str = "claude-haiku-4-5-20251001"
    default_focus: str = "full"
    default_format: str = "rich"
    save_history: bool = False
    history_path: Path = field(default_factory=lambda: Path.home() / ".diffmind" / "history.jsonl")

_cached: DiffmindConfig | None = None

def get_config() -> DiffmindConfig:
    """Return cached config, loading from ~/.diffmind.toml on first call."""
    global _cached
    if _cached is not None:
        return _cached
    cfg = DiffmindConfig()
    if _CONFIG_PATH.exists():
        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            raw = tomllib.loads(_CONFIG_PATH.read_text())
            if "model" in raw: cfg.default_model = str(raw["model"])
            if "focus" in raw: cfg.default_focus = str(raw["focus"])
            if "format" in raw: cfg.default_format = str(raw["format"])
            if "save_history" in raw: cfg.save_history = bool(raw["save_history"])
            if "history_path" in raw: cfg.history_path = Path(raw["history_path"])
        except Exception:
            pass
    _cached = cfg
    return cfg
