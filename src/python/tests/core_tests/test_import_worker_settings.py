"""Tests for the per-job import-settings wiring in `beetkeeper.core.import_worker`.

`_apply_job_import_config` overlays a job's persisted settings onto beets' process-global config (which the
running `ImportSession` reads), and `_job_loghandler` builds the `beet import -l` file handler. These
manipulate the global beets config directly (restored by a fixture); no real import or network runs.
"""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from beetkeeper.core.import_jobs import ImportJob, ImportJobStatus
from beetkeeper.core.import_worker import _apply_job_import_config, _job_loghandler


def _job(**overrides: Any) -> ImportJob:
    defaults: dict[str, Any] = {
        "id": "job-1",
        "status": ImportJobStatus.RUNNING,
        "paths": ["/music/a"],
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return ImportJob(**defaults)


@pytest.fixture
def restore_beets_import_config() -> Iterator[Any]:
    """Yield beets' global `import` config view, restoring the keys the worker overlays afterwards."""
    from beets import config

    originals = {key: config["import"][key].get() for key in ("group_albums", "flat", "set_fields")}
    try:
        yield config["import"]
    finally:
        for key, value in originals.items():
            config["import"][key] = value


@pytest.mark.usefixtures("restore_beets_import_config")
def test_apply_job_import_config_overlays_job_settings() -> None:
    from beets import config

    _apply_job_import_config(_job(group_albums=True, flat=True, set_fields={"genre": "Jazz"}))

    assert config["import"]["group_albums"].get(bool) is True
    assert config["import"]["flat"].get(bool) is True
    assert config["import"]["set_fields"].get() == {"genre": "Jazz"}


@pytest.mark.usefixtures("restore_beets_import_config")
def test_apply_job_import_config_does_not_leak_between_jobs() -> None:
    from beets import config

    _apply_job_import_config(_job(group_albums=True, flat=True, set_fields={"genre": "Jazz"}))
    _apply_job_import_config(_job())

    assert config["import"]["group_albums"].get(bool) is False
    assert config["import"]["flat"].get(bool) is False
    assert config["import"]["set_fields"].get() == {}


def test_job_loghandler_is_none_without_logpath() -> None:
    assert _job_loghandler(_job()) is None


def test_job_loghandler_writes_to_the_configured_file(tmp_path: Path) -> None:
    logpath = tmp_path / "import.log"
    handler = _job_loghandler(_job(logpath=str(logpath)))
    assert handler is not None
    try:
        handler.emit(logging.LogRecord("beets-import", logging.INFO, __file__, 0, "import started", None, None))
    finally:
        handler.close()
    assert "import started" in logpath.read_text(encoding="utf-8")


def test_job_loghandler_appends_across_jobs(tmp_path: Path) -> None:
    """Two jobs logging to the same path accumulate lines (`logging.FileHandler` defaults to append mode)."""
    logpath = tmp_path / "import.log"
    for line in ("first import", "second import"):
        handler = _job_loghandler(_job(logpath=str(logpath)))
        assert handler is not None
        try:
            handler.emit(logging.LogRecord("beets-import", logging.INFO, __file__, 0, line, None, None))
        finally:
            handler.close()
    text = logpath.read_text(encoding="utf-8")
    assert "first import" in text and "second import" in text
