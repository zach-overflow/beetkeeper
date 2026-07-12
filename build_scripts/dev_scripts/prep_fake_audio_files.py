"""Manage the fake (empty-but-tagged) FLAC files the manual test server uses to exercise imports.

`create` materializes one album directory per JSON file in `fake_tag_data/` — each names an `albumdirname`
and the per-track FLAC tags — so the test container's downloads directory has realistic albums to import;
`remove` deletes them (and anything imports left behind) again. Runs inside the test container via the app
PEX (see `test_container_init.sh`), which provides `click` and `mutagen` and keeps all created files
container-local.
"""

import json
from pathlib import Path

import click
from mutagen.flac import FLAC

_FAKE_TAG_DATA_DIRPATH = Path(__file__).parent / "fake_tag_data"

# mutagen cannot create a FLAC from nothing (an empty file fails to parse), so fake files start from the
# smallest valid stream: the 'fLaC' marker + one last-metadata-block STREAMINFO declaring 4096-sample
# blocks, 44.1 kHz / stereo / 16-bit, zero total samples, and no audio frames at all.
_MINIMAL_FLAC_STREAM = (
    b"fLaC"
    + b"\x80\x00\x00\x22"
    + b"\x10\x00" * 2
    + b"\x00\x00\x00" * 2
    + ((44100 << 44) | (1 << 41) | (15 << 36)).to_bytes(8, "big")
    + b"\x00" * 16
)


@click.group(help="Utility for managing fake audio files in the lifespan of a test-server container.")
@click.option(
    "-d",
    "--dirpath",
    required=True,
    help="The directory in which to place the audio file stubs. Should be the path of the 'raw' non-beet ingested inputs",
    type=click.Path(file_okay=False, dir_okay=True, exists=True, path_type=Path),
)
@click.pass_context
def cli(ctx: click.Context, dirpath: Path) -> None:
    ctx.obj = dirpath


@cli.command(help="Creates fake audio file stubs with searchable tags.")
@click.pass_obj
def create(dirpath: Path) -> None:
    for tag_data_filepath in sorted(_FAKE_TAG_DATA_DIRPATH.glob("*.json")):
        album_data = json.loads(tag_data_filepath.read_text(encoding="utf-8"))
        album_dirpath = dirpath / album_data["albumdirname"]
        album_dirpath.mkdir(exist_ok=True)
        for track_filename, tags in album_data["tracks"].items():
            _create_fake_audio_file(album_dirpath / track_filename, tags)


@cli.command(help="Removes all fake audio files from the `create` command + during the test server run.")
@click.pass_obj
def remove(dirpath: Path) -> None:
    for flac_filepath in sorted(dirpath.rglob("*.flac")):
        flac_filepath.unlink()
        click.echo(f"Removed '{flac_filepath}'")
    for child_dirpath in sorted((path for path in dirpath.rglob("*") if path.is_dir()), reverse=True):
        if not any(child_dirpath.iterdir()):
            child_dirpath.rmdir()
            click.echo(f"Removed empty directory '{child_dirpath}'")


def _create_fake_audio_file(filepath: Path, tags: dict[str, list[str]]) -> None:
    """Creates a fake FLAC file at `filepath` with the given tags."""
    filepath.write_bytes(_MINIMAL_FLAC_STREAM)
    audio = FLAC(filepath)
    for tag_name, values in tags.items():
        audio[tag_name] = values
    audio.save()
    click.echo(f"Created mock FLAC file with metadata at '{filepath}'")


if __name__ == "__main__":
    cli()
