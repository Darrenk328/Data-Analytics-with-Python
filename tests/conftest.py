"""Shared fixtures: isolated cache/config dirs and a DataStore built from tiny real CSVs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def _isolated_dirs(tmp_path_factory: pytest.TempPathFactory) -> None:
    os.environ["SKYSCOPE_CACHE_DIR"] = str(tmp_path_factory.mktemp("cache"))
    os.environ["SKYSCOPE_CONFIG_DIR"] = str(tmp_path_factory.mktemp("config"))


@pytest.fixture(scope="session")
def mini_store():
    """DataStore from tests/fixtures/*.csv (~30 real airports)."""
    from skyscope.data.store import build_store

    return build_store({stem: FIXTURES / f"{stem}.csv"
                        for stem in ("airports", "runways", "countries", "regions")})


@pytest.fixture(scope="session")
def store():
    """The full DataStore from the bundled snapshot (offline)."""
    from skyscope.config import RUNTIME
    from skyscope.data.store import get_store

    RUNTIME.offline = True
    return get_store()
