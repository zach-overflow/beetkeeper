"""Seed the manual test server with fake beets listener events for spot-checking the events page.

Event records are only ever created from plugin pushes to the `/api/events/*` routes (the server never
synthesizes them), so this seeder impersonates the `beetkeeper_plugin` client: it waits for the server's
health endpoint, logs in, then POSTs plugin-shaped payloads covering each events-UI rendering — a merged
album-import push pair, a merged singleton-import pair (release name with no beets album id), album/track
removals, an unpaired `import_task_files` push, and a legacy name-less push (beets-id fallback). Runs
inside the test container via the app PEX (see `test_container_init.sh`), which provides `click`/`httpx`.
"""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import click
import httpx

_HEALTH_PATH = "/api/health"
_LOGIN_PATH = "/api/auth/login"


def _fs_item(
    pushed_at: str, beets_item_id: int, beets_album_id: int | None, title: str, album: str, path: str
) -> dict[str, Any]:
    return {
        "event_type": "import_task_files",
        "pushed_at": pushed_at,
        "track_fields": {"id": beets_item_id, "album_id": beets_album_id, "title": title, "album": album, "path": path},
    }


def _fake_event_pushes(now: datetime) -> list[tuple[str, dict[str, Any]]]:
    """`(route subpath, payload)` pairs, oldest first; each import's `import_task_files` push sits a few
    seconds before its imported-event push so the events UI folds them (its merge skew is one minute)."""

    def at(minutes: float, seconds: float = 0) -> str:
        return (now - timedelta(minutes=minutes, seconds=seconds)).isoformat()

    album_tracks = [(101, "Concrete Sky"), (102, "Elevator Hymn"), (103, "Load-Bearing Heart")]
    return [
        ("/api/events/album", {"event_type": "album_imported", "pushed_at": at(30), "album_fields": {"id": 300}}),
        (
            "/api/events/filesystem",
            {
                "event_type": "import_task_files",
                "pushed_at": at(25),
                "choice_flag": "APPLY",
                "source_paths": ["/downloads/demos/day1", "/downloads/demos/day2"],
                "imported_items": [
                    _fs_item(
                        at(25),
                        beets_item_id=210 + index,
                        beets_album_id=210,
                        title=f"Sketch No. {index}",
                        album="Half-Finished Demos",
                        path=f"/test_dirs/music/Half-Finished Demos/{index:02d} Sketch No. {index}.flac",
                    )
                    for index in (1, 2)
                ],
            },
        ),
        (
            "/api/events/album",
            {
                "event_type": "album_removed",
                "pushed_at": at(15),
                "album_fields": {"id": 195, "album": "Farewell and Goodnight"},
            },
        ),
        (
            "/api/events/track",
            {"event_type": "item_removed", "pushed_at": at(10), "track_fields": {"id": 950, "title": "Static Bloom"}},
        ),
        (
            "/api/events/filesystem",
            {
                "event_type": "import_task_files",
                "pushed_at": at(5, 2),
                "choice_flag": "ASIS",
                "source_paths": ["/downloads/interstate lullaby.flac"],
                "imported_items": [
                    _fs_item(
                        at(5, 2),
                        beets_item_id=501,
                        beets_album_id=None,
                        title="Interstate Lullaby",
                        album="Late Night Radio, Vol. 3",
                        path="/test_dirs/music/singles/Interstate Lullaby.flac",
                    )
                ],
            },
        ),
        (
            "/api/events/track",
            {
                "event_type": "item_imported",
                "pushed_at": at(5),
                "track_fields": {"id": 501, "title": "Interstate Lullaby", "album": "Late Night Radio, Vol. 3"},
            },
        ),
        (
            "/api/events/filesystem",
            {
                "event_type": "import_task_files",
                "pushed_at": at(0, 2),
                "choice_flag": "APPLY",
                "source_paths": ["/downloads/The Modal Fjords - Songs About Buildings (2019)"],
                "imported_items": [
                    _fs_item(
                        at(0, 2),
                        beets_item_id=track_id,
                        beets_album_id=42,
                        title=title,
                        album="Songs About Buildings",
                        path=f"/test_dirs/music/The Modal Fjords/Songs About Buildings/{index:02d} {title}.flac",
                    )
                    for index, (track_id, title) in enumerate(album_tracks, start=1)
                ],
            },
        ),
        (
            "/api/events/album",
            {
                "event_type": "album_imported",
                "pushed_at": at(0),
                "album_fields": {"id": 42, "album": "Songs About Buildings", "albumartist": "The Modal Fjords"},
            },
        ),
    ]


def _wait_for_server(client: httpx.Client, wait_seconds: int) -> None:
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            if client.get(_HEALTH_PATH).status_code == httpx.codes.OK:
                return
        except httpx.TransportError:
            pass
        if time.monotonic() >= deadline:
            raise click.ClickException(f"Server at '{client.base_url}' not healthy after {wait_seconds}s.")
        time.sleep(1)


def _auth_headers(client: httpx.Client, username: str, password: str) -> dict[str, str]:
    """A bearer-token header from the login route, or no header when login protection is disabled."""
    response = client.post(_LOGIN_PATH, json={"username": username, "password": password})
    if response.status_code == httpx.codes.OK:
        return {"Authorization": f"Bearer {response.json()['token']}"}
    click.echo(f"Login returned {response.status_code}; pushing events without auth.")
    return {}


@click.command(help="Pushes fake beets listener events to a running beetkeeper test server.")
@click.option("--server-url", default="http://127.0.0.1:8337", show_default=True, help="Base URL of the test server.")
@click.option("--username", default="admin", show_default=True, help="Login username (see test_beets_conf.yaml).")
@click.option("--password", default="admin", show_default=True, help="Login password (see test_beets_conf.yaml).")
@click.option("--wait-seconds", default=60, show_default=True, type=int, help="How long to wait for server startup.")
def cli(server_url: str, username: str, password: str, wait_seconds: int) -> None:
    with httpx.Client(base_url=server_url.rstrip("/"), timeout=10.0) as client:
        _wait_for_server(client, wait_seconds)
        headers = _auth_headers(client, username, password)
        for subpath, payload in _fake_event_pushes(datetime.now(UTC)):
            client.post(subpath, json=payload, headers=headers).raise_for_status()
            click.echo(f"Seeded '{payload['event_type']}' event via POST {subpath}")
    click.echo("Fake event data seeded; open /events to spot-check the rendering.")


if __name__ == "__main__":
    cli()
