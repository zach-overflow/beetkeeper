"""
Fixtures for opt-in integration tests that exercise the API against a REAL beets library built from real
audio files on the host machine.

Opt-in: every test in this directory is tagged `requires_host_sources` and is SKIPPED unless pytest is
invoked with that marker selected (e.g. `pytest -m requires_host_sources`). The host data location is
given by the `BEETKEEPER_HOST_TEST_DIRPATH` env var, pointing at a directory laid out as:

    /<BEETKEEPER_HOST_TEST_DIRPATH>
    ├── config.yaml          # the host beets config
    └── raw/                 # real, un-imported audio (beets imports FROM here)
        ├── <album dir>/...

To preserve the host files, the fixtures copy the raw audio into a temp dir and write a COPY of the beets
config whose `library`/`directory` keys point inside that temp dir. A throwaway beets library is then
populated from the copied audio's tags (no network, no plugins, no full import pipeline), and the API is
pointed at it. Nothing under the host directory is modified.
"""

import os
import shutil
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Final

import pytest
from ruamel.yaml import YAML

_REQUIRED_ENVVAR: Final[str] = "BEETKEEPER_HOST_TEST_DIRPATH"
_MARKER: Final[str] = "requires_host_sources"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Tag every test in THIS directory with `requires_host_sources`, and skip them unless opted in.

    These tests require user-specified host directories with real audio, so by default (no `-m
    requires_host_sources`) they are skipped; pass `-m requires_host_sources` to run them. NOTE: this hook
    receives the whole session's items, so we filter to this directory's tests (else we'd skip everything).
    See: https://docs.pytest.org/en/9.0.x/reference/reference.html#pytest.hookspec.pytest_collection_modifyitems
    """
    here = Path(__file__).parent
    opted_in = _MARKER in (config.getoption("markexpr") or "")
    skip_marker = pytest.mark.skip(reason=f"opt-in integration test; run with `-m {_MARKER}`")
    for item in items:
        if here not in item.path.parents:
            continue  # only affect integration tests in this directory
        item.add_marker(getattr(pytest.mark, _MARKER))
        if not opted_in:
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def tmp_base_dirpath(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped temp dir holding the copies of the host raw audio + the rewritten beets config.

    See: https://docs.pytest.org/en/9.0.x/how-to/tmp_path.html#the-tmp-path-factory-fixture
    """
    return tmp_path_factory.mktemp("base")


@pytest.fixture(scope="session")
def src_config_filepath() -> Path:
    """Path to the host beets config: `<BEETKEEPER_HOST_TEST_DIRPATH>/config.yaml`."""
    if not (raw_envvar_val := os.getenv(_REQUIRED_ENVVAR)):
        raise ValueError(f"Missing required environment variable '{_REQUIRED_ENVVAR}'. Cannot run integration tests.")
    config_filepath = Path(raw_envvar_val).resolve() / "config.yaml"
    if not config_filepath.is_file():
        raise ValueError(f"Expected a beets config at '{config_filepath}' (under ${_REQUIRED_ENVVAR}).")
    return config_filepath


@pytest.fixture(scope="session")
def src_config_data(src_config_filepath: Path) -> dict[str, Any]:
    """The host beets config parsed into a (round-trippable) mapping."""
    return YAML().load(src_config_filepath.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def tmp_raw_dirpath(tmp_base_dirpath: Path, src_config_filepath: Path) -> Path:
    """A temp copy of the host `raw/` (un-imported) audio, so the host files are never touched."""
    host_raw_dirpath = src_config_filepath.parent / "raw"
    if not host_raw_dirpath.exists():
        raise ValueError(f"Missing expected 'raw' unprocessed music directory at {host_raw_dirpath}.")
    tmp_dirpath = tmp_base_dirpath / "raw"
    shutil.copytree(host_raw_dirpath, tmp_dirpath, dirs_exist_ok=True)
    return tmp_dirpath


@pytest.fixture(scope="session")
def tmp_dst_dirpath(tmp_base_dirpath: Path, src_config_data: dict[str, Any]) -> Path:
    """A temp copy of the host beets `directory` (already-imported/tagged music), if a test needs it.

    Not used by the query tests below (which build a library from `raw` instead), but kept for tests that
    want to operate on a copy of a pre-imported library directory.
    """
    host_directory = Path(str(src_config_data["directory"])).resolve()
    tmp_dirpath = tmp_base_dirpath / "dst"
    shutil.copytree(host_directory, tmp_dirpath, dirs_exist_ok=True)
    return tmp_dirpath


@pytest.fixture(scope="session")
def tmp_beets_config_filepath(tmp_base_dirpath: Path, src_config_data: dict[str, Any], tmp_raw_dirpath: Path) -> Path:
    """A copy of the host beets config with `library`/`directory` rewritten into the temp base dir.

    `directory` is pointed at the copied raw audio (`tmp_raw_dirpath`); `library` at a fresh db path that
    `populated_beets_config` fills in.
    """
    src_config_data["directory"] = str(tmp_raw_dirpath)
    src_config_data["library"] = str(tmp_base_dirpath / os.path.basename(str(src_config_data["library"])))
    # beets' plugin registry is process-global; disable plugins in tests so no network-backed autotag plugin
    # (e.g. musicbrainz/discogs/bandcamp) ever loads into this process — tests must never make real network
    # calls (see CLAUDE.md). `open_library` loads whatever this lists, so an empty list keeps it offline.
    src_config_data["plugins"] = []
    tmp_conf_filepath = tmp_base_dirpath / "config.yaml"
    with tmp_conf_filepath.open("w", encoding="utf-8") as conf_file:
        YAML().dump(src_config_data, conf_file)
    return tmp_conf_filepath


@pytest.fixture(scope="session")
def populated_beets_config(tmp_beets_config_filepath: Path, tmp_raw_dirpath: Path) -> Path:
    """Build a real beets library from the copied audio's tags and return the beets config path.

    Reads each audio file's existing tags (mediafile — no network, no autotag, no plugins) and groups files
    by directory into albums. The resulting library matches what `beetkeeper.core.open_library` opens.
    """
    from beets import config as beets_config
    from beets.library import Item, Library
    from beets.util import bytestring_path

    beets_config.set_file(str(tmp_beets_config_filepath))
    library = Library(beets_config["library"].as_filename(), beets_config["directory"].as_filename())

    audio_by_dir: dict[Path, list[Path]] = defaultdict(list)
    for audio_path in tmp_raw_dirpath.rglob("*"):
        if audio_path.suffix.lower() in {".flac", ".mp3", ".m4a", ".ogg", ".opus"}:
            audio_by_dir[audio_path.parent].append(audio_path)
    for audio_paths in audio_by_dir.values():
        items = [Item.from_path(bytestring_path(str(path))) for path in sorted(audio_paths)]
        if items:
            library.add_album(items)
    return tmp_beets_config_filepath


@pytest.fixture
async def integration_client(populated_beets_config: Path) -> AsyncIterator[Any]:
    """An ASGI client whose `get_beets_library` dependency is bound to the populated host-backed library."""
    from httpx import ASGITransport, AsyncClient

    from beetkeeper.api.dependencies import get_beets_library
    from beetkeeper.api.fastapi_app import beetkeeper_app
    from beetkeeper.core import BeetsLibrary

    library = BeetsLibrary(populated_beets_config)
    beetkeeper_app.dependency_overrides[get_beets_library] = lambda: library
    try:
        async with AsyncClient(transport=ASGITransport(app=beetkeeper_app), base_url="http://testclient") as client:
            yield client
    finally:
        beetkeeper_app.dependency_overrides.clear()
