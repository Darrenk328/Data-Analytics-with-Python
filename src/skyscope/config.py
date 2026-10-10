"""Paths, runtime flags and persisted user settings (units, default aircraft, favourites)."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir

APP_NAME = "skyscope"
PACKAGE_DIR = Path(__file__).resolve().parent
SNAPSHOT_DIR = PACKAGE_DIR / "snapshot"


def cache_dir() -> Path:
    """Directory for downloaded data, pickles and logs (override with SKYSCOPE_CACHE_DIR)."""
    path = Path(os.environ.get("SKYSCOPE_CACHE_DIR") or user_cache_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    """Directory for settings.json and shell history (override with SKYSCOPE_CONFIG_DIR)."""
    path = Path(os.environ.get("SKYSCOPE_CONFIG_DIR") or user_config_dir(APP_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Runtime:
    """Process-wide flags set once by the CLI."""

    offline: bool = False
    debug: bool = False


RUNTIME = Runtime()


@dataclass
class Settings:
    """User preferences persisted to settings.json."""

    units: str = "metric"  # "metric" or "imperial"
    aircraft: str = "737-800"
    favourites: list[str] = field(default_factory=list)
    kg_per_passenger: float = 100.0

    @classmethod
    def load(cls) -> Settings:
        """Read settings from disk, falling back to defaults on any problem."""
        path = config_dir() / "settings.json"
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        try:
            return cls(**known)
        except TypeError:
            return cls()

    def save(self) -> None:
        """Write settings to disk (errors are swallowed: settings are a convenience)."""
        with contextlib.suppress(OSError):
            (config_dir() / "settings.json").write_text(json.dumps(asdict(self), indent=2))
