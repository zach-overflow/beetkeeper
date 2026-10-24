"""Shared core_tests fixtures and stand-ins: a throwaway beets `Library`, a downloads root, and `Attrs`."""

from pathlib import Path
from typing import Any

import pytest
from beets.library import Library


class Attrs:
    """
    Minimal attribute bag standing in for beets objects (`Album`/`Item`, tasks, matches).

    Hashable by identity, so instances also work as `mapping` dict keys.
    """

    def __init__(self, **attrs: Any) -> None:
        self.__dict__.update(attrs)


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return Library(str(tmp_path / "lib.db"), str(tmp_path / "music"))


@pytest.fixture
def downloads(tmp_path: Path) -> Path:
    path = tmp_path / "downloads"
    path.mkdir()
    return path
