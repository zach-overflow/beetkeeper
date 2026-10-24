"""A fake download-client API for the manual test server, answering the downloader hook's lookups.

Impersonates a download client's search endpoint (the shape of qBittorrent's `/api/v2/torrents/info`) so the
test container can exercise the search page's **Find via downloader** button and the clean-slate import it
leads to. It knows only the fake albums `prep_fake_audio_files.py` creates: a lookup whose `name` query param
matches one of their album titles or folder names (case-insensitively, or as a substring either way — an
autotagged import may have retitled the album) answers with that folder under the downloads path; anything
else answers an empty list. Stdlib HTTP only, so it runs inside the test container via the app PEX like the
other dev scripts (see `test_container_init.sh`, which starts it before the server).
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

import click

_FAKE_TAG_DATA_DIRPATH = Path(__file__).parent / "fake_tag_data"


def _catalogue() -> dict[str, str]:
    """Lower-cased album titles and folder names of the fake albums, each mapped to its folder name."""
    catalogue: dict[str, str] = {}
    for tag_data_filepath in sorted(_FAKE_TAG_DATA_DIRPATH.glob("*.json")):
        album_data = json.loads(tag_data_filepath.read_text(encoding="utf-8"))
        folder = album_data["albumdirname"]
        catalogue[folder.lower()] = folder
        for tags in album_data["tracks"].values():
            for title in tags.get("album", []):
                catalogue[title.strip().lower()] = folder
    return catalogue


class _SearchHandler(BaseHTTPRequestHandler):
    catalogue: ClassVar[dict[str, str]] = {}
    downloads_path: ClassVar[Path] = Path("/downloads")
    endpoint: ClassVar[str] = "/api/v2/torrents/info"

    def do_GET(self) -> None:  # noqa: N802  # http.server's dispatch requires this exact name
        url = urlparse(self.path)
        if url.path != self.endpoint:
            self._reply(404, {"error": f"unknown endpoint {url.path}"})
            return
        name = parse_qs(url.query).get("name", [""])[0].strip().lower()
        folder = self._lookup(name)
        results = [{"name": folder, "content_path": str(self.downloads_path / folder)}] if folder else []
        self._reply(200, results)

    def _lookup(self, name: str) -> str | None:
        if not name:
            return None
        if name in self.catalogue:
            return self.catalogue[name]
        return next((folder for key, folder in self.catalogue.items() if name in key or key in name), None)

    def _reply(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002  # http.server's own signature
        click.echo(f"fake downloader api: {format % args}")


@click.command(help="Serve a fake download-client search API over the fake albums' folders.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Interface to bind.")
@click.option("--port", default=8338, show_default=True, type=int, help="Port to listen on.")
@click.option(
    "--downloads-path",
    default="/downloads",
    show_default=True,
    help="Where the fake albums' folders live from the beetkeeper server's point of view.",
)
def main(host: str, port: int, downloads_path: str) -> None:
    _SearchHandler.catalogue = _catalogue()
    _SearchHandler.downloads_path = Path(downloads_path)
    click.echo(
        f"fake downloader api: serving {len(set(_SearchHandler.catalogue.values()))} fake album(s) on "
        f"http://{host}:{port}{_SearchHandler.endpoint}"
    )
    ThreadingHTTPServer((host, port), _SearchHandler).serve_forever()


if __name__ == "__main__":
    main()
