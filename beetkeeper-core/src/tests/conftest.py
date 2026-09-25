"""Shared fixtures: anyio backend selection, temp-file SQLite URLs, an alembic Config, a migrated DB, and a
generator of small real audio files (for tests that drive beets' importer over actual media)."""

import os
import wave
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from beetkeeper.core import ImportStore
from beetkeeper.db import make_engine, make_sessionmaker, migrations


@pytest.fixture(autouse=True, scope="session")
def isolated_beets_config_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Point beets' global (lazily-read) config at an empty per-session dir, never a developer's real one."""
    beets_dir = tmp_path_factory.mktemp("beets-config")
    os.environ["BEETSDIR"] = str(beets_dir)
    return beets_dir


TaggedWavWriter = Callable[..., Path]


@pytest.fixture
def make_tagged_wav() -> TaggedWavWriter:
    """Write a tiny, valid, tagged WAV file: `make_tagged_wav(path, title=..., artist=..., ...)`.

    beets reads tags through mediafile, which supports ID3 tags inside RIFF/WAV, so a stdlib-generated WAV plus
    a `MediaFile.save()` is the cheapest real audio file the importer will accept (beets ships no fixture audio).
    Any keyword is set as a mediafile tag field (`title`, `artist`, `album`, `albumartist`, `track`, `tracktotal`,
    `disc`, `disctotal`, `mb_trackid`, ...).
    """

    def _write(path: Path, **tags: Any) -> Path:
        from mediafile import MediaFile  # type: ignore[import-untyped]

        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b"\x00\x00" * 800)
        media = MediaFile(str(path))
        for field, value in tags.items():
            setattr(media, field, value)
        media.save()
        return path

    return _write


@pytest.fixture
def anyio_backend() -> str:
    """Run all `@pytest.mark.anyio` tests on asyncio (we do not target trio). See CLAUDE.md test rules."""
    return "asyncio"


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    """A throwaway SQLite file path under pytest's tmp_path (the file is created by the migrations)."""
    return tmp_path / "beetkeeper_test.db"


@pytest.fixture
def async_url(db_file: Path) -> str:
    return f"sqlite+aiosqlite:///{db_file}"


@pytest.fixture
def sync_url(db_file: Path) -> str:
    return f"sqlite:///{db_file}"


@pytest.fixture
def alembic_cfg(async_url: str, sync_url: str) -> Config:
    """An alembic Config for the packaged environment, pointed at the temp DB."""
    return migrations.make_alembic_config(async_url=async_url, sync_url=sync_url)


@pytest.fixture
def migrated_db(alembic_cfg: Config, async_url: str) -> str:
    """Applies all migrations to a fresh temp DB and returns its async (aiosqlite) URL."""
    migrations.upgrade(alembic_cfg, "head")
    return async_url


@pytest.fixture
def import_store(session_factory: async_sessionmaker[AsyncSession]) -> ImportStore:
    """An `ImportStore` bound to the migrated temp DB (no worker runs unless the test starts one)."""
    return ImportStore(session_factory)


@pytest.fixture
async def session_factory(migrated_db: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """An `async_sessionmaker` bound to a freshly-migrated temp DB (FK enforcement enabled)."""
    engine = make_engine(migrated_db)
    try:
        yield make_sessionmaker(engine)
    finally:
        await engine.dispose()
