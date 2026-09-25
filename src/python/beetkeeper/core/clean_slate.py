"""
Clean-slate imports: remove one library entry, then import its raw source folder afresh.

beets' own reimport (`beet import -L`) only re-tags files the library already points at, so it cannot recover
a track whose file is gone or that an earlier import dropped. A clean slate sidesteps beets' reimport
machinery entirely: `remove_entry` takes the entry out of the library the way `beet remove -d` would (rows,
the files inside the beets directory, the album art), and the import worker then runs an ordinary path import
over the source folder. Nothing is carried over — not flexible attributes, not the added-date — which is
what "clean slate" means and what `preview` spells out before anything is touched. The one exception is the
flexible attributes named by `preserve_fields` (in beetkeeper, the downloader hook's search fields, which identify
the entry's download): `preview` reports their values, and the import worker re-applies them to the fresh import
through beets' `--set` (see `import_worker._apply_job_import_config`).

Safety rules, enforced by `preview` (the worker re-runs it as a guard right before removing anything):
  * the source must be a real path under beetkeeper's `downloads_path` and outside the beets directory;
  * for an album it must hold exactly one album folder with at least one readable audio file, for a standalone
    track exactly one readable audio file;
  * a source holding fewer audio files than the entry currently has on disk needs an explicit opt-in;
  * only files inside the beets directory are ever deleted, and never anything under the source path.

`file_health` powers the search page's per-row "files missing" marker, which is how entries in need of a
clean slate are found. This module is the only new place that touches beets internals (see `core.library`).
"""

import os
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from beets import config as beets_config
from beets.importer.tasks import albums_in_dir
from beets.library import Album, Item, LibModel, Library
from beets.library.exceptions import ReadError
from beets.util import ancestry, bytestring_path, displayable_path, normpath, prune_dirs, syspath
from beets.util import remove as remove_file

from beetkeeper.core.import_jobs import CleanSlatePreview, CleanSlateTarget

CleanSlateErrorKind = Literal["not_found", "invalid", "needs_confirmation"]


class CleanSlateError(ValueError):
    """A clean slate cannot run: the entry is unknown, the preview found a blocking error, or it needs opt-in."""

    def __init__(self, kind: CleanSlateErrorKind, message: str, preview: CleanSlatePreview | None = None) -> None:
        """Carry the failure `kind` (mapped to an HTTP status by the API) and the preview it came from, if any."""
        super().__init__(message)
        self.kind = kind
        self.preview = preview


@dataclass(frozen=True)
class AlbumFileHealth:
    """How complete an album's files are: rows vs. files on disk vs. the track total its tags claim."""

    item_count: int
    files_present: int
    expected_tracks: int | None

    @property
    def files_missing(self) -> int:
        """Rows whose file is gone from disk."""
        return self.item_count - self.files_present

    @property
    def short_of_release(self) -> int:
        """Tracks the album's tags list beyond the rows the library holds (0 when unknown or complete)."""
        if self.expected_tracks is None:
            return 0
        return max(self.expected_tracks - self.item_count, 0)

    @property
    def incomplete(self) -> bool:
        """Whether anything is missing, by either measure."""
        return self.files_missing > 0 or self.short_of_release > 0


@dataclass(frozen=True)
class RemovedEntry:
    """What `remove_entry` did: the ids it took out of the library and the files it deleted or left alone."""

    target: CleanSlateTarget
    item_ids: list[int]
    deleted_paths: list[str]
    kept_paths: list[str]
    deleted_art: str | None


@dataclass(frozen=True)
class _Entry:
    label: str
    album: Album | None
    items: list[Item]


@dataclass(frozen=True)
class _DeletionPlan:
    to_delete: list[bytes]
    kept: list[bytes]
    art: bytes | None


@dataclass(frozen=True)
class _SourceScan:
    errors: list[str]
    audio_files: int
    album_groups: int
    common_tags: tuple[str, str] | None


def saved_id(model: LibModel) -> int:
    """The id of a model that is in the library (beets types `id` as optional for unsaved models)."""
    assert model.id is not None
    return model.id


def file_exists(item: Item) -> bool:
    """Whether the item's file is still on disk."""
    return os.path.exists(syspath(item.path))


def expected_tracks(items: Sequence[Item]) -> int | None:
    """
    The track total an album's tags claim, computed as beets' `Album.albumtotal` does (None when unknown).

    Takes the album's items (which carry the album-level `disctotal`) so a page of albums needs one items
    query rather than one per album.
    """
    if not items:
        return None
    disctotal = int(items[0].disctotal or 0)
    if disctotal <= 1 or not beets_config["per_disc_numbering"].get(bool):
        return int(items[0].tracktotal or 0) or None
    seen: set[int] = set()
    total = 0
    for item in items:
        if item.disc in seen:
            continue
        seen.add(item.disc)
        total += int(item.tracktotal or 0)
        if len(seen) == disctotal:
            break
    return total or None


def file_health(items: Sequence[Item]) -> AlbumFileHealth:
    """Rows vs. files on disk vs. claimed track total for one album's items."""
    return AlbumFileHealth(
        item_count=len(items),
        files_present=sum(1 for item in items if file_exists(item)),
        expected_tracks=expected_tracks(items),
    )


def preview(
    lib: Library,
    target: CleanSlateTarget,
    source_path: str,
    *,
    downloads_path: Path,
    allow_fewer_files: bool = False,
    preserve_fields: Collection[str] = (),
) -> CleanSlatePreview:
    """
    Dry-run a clean slate of `target` from `source_path` (read-only; see the module docstring's rules).

    `preserve_fields` names the flexible attributes whose values the clean slate carries onto the fresh import;
    they are reported as `fields_preserved` and left out of `flexible_attributes_lost`.

    Raises `CleanSlateError("not_found")` when no library entry has the target's id. Every other problem is
    reported inside the returned preview (`errors`, `warnings`, `needs_confirmation`); `require_ok` turns those
    into the matching `CleanSlateError`.
    """
    entry = _load_entry(lib, target)
    if entry is None:
        raise CleanSlateError("not_found", f"No beets {target.subject} with id {target.beets_id}.")
    preserved = _preserved_fields(entry, preserve_fields)
    errors: list[str] = []
    warnings: list[str] = []
    if target.subject == "track" and entry.items[0].album_id:
        errors.append(
            f"This track belongs to album #{entry.items[0].album_id}; run the clean slate on that album instead."
        )
    present = [item for item in entry.items if file_exists(item)]
    missing = [item for item in entry.items if not file_exists(item)]
    source = _normalized_source(source_path)
    scan = _scan_source(lib, target, source, downloads_path)
    errors.extend(scan.errors)
    plan = _deletion_plan(lib, entry, source)
    tracks_expected = expected_tracks(entry.items) if target.subject == "album" else None

    needs_confirmation = False
    if not scan.errors and scan.audio_files < len(present):
        warnings.append(
            f"The source has {scan.audio_files} audio file(s) but the library currently has {len(present)} on "
            "disk: the clean slate would delete files the source cannot replace."
        )
        needs_confirmation = not allow_fewer_files
    if not missing and not scan.errors:
        warnings.append("Every file of this entry is still on disk; the clean slate replaces them all anyway.")
    if tracks_expected and scan.audio_files and scan.audio_files < tracks_expected:
        warnings.append(
            f"The source has {scan.audio_files} audio file(s) but the album's tags list {tracks_expected} tracks."
        )
    if scan.common_tags is not None and target.subject == "album":
        source_label = f"{scan.common_tags[0] or '?'} - {scan.common_tags[1] or '?'}"
        if source_label != entry.label:
            warnings.append(f"The source files are tagged '{source_label}'; the library entry is '{entry.label}'.")

    return CleanSlatePreview(
        subject=target.subject,
        beets_id=target.beets_id,
        label=entry.label,
        item_count=len(entry.items),
        files_present=len(present),
        missing_paths=[displayable_path(item.path) for item in missing],
        expected_tracks=tracks_expected,
        files_to_delete=[displayable_path(path) for path in plan.to_delete],
        files_kept_outside_library=[displayable_path(path) for path in plan.kept],
        art_to_delete=displayable_path(plan.art) if plan.art else None,
        flexible_attributes_lost=_flexible_attributes(entry, excluding=preserved),
        fields_preserved=preserved,
        source_path=displayable_path(source),
        source_audio_files=scan.audio_files,
        source_album_groups=scan.album_groups,
        warnings=warnings,
        errors=errors,
        needs_confirmation=needs_confirmation,
    )


def require_ok(preview_result: CleanSlatePreview) -> None:
    """Raise the `CleanSlateError` a non-`ok` preview implies (blocking errors first, then the opt-in)."""
    if preview_result.errors:
        raise CleanSlateError("invalid", " ".join(preview_result.errors), preview_result)
    if preview_result.needs_confirmation:
        raise CleanSlateError(
            "needs_confirmation",
            "The source has fewer audio files than the library entry has on disk; set allow_fewer_files to proceed.",
            preview_result,
        )


def remove_entry(
    lib: Library, target: CleanSlateTarget, source_path: str, *, narrate: Callable[[str], None]
) -> RemovedEntry:
    """
    Take `target` out of the library like `beet remove -d`, minus anything outside the beets directory.

    Rows always go. A file goes only when it lies inside the beets directory and not under `source_path`
    (mirroring how beets itself removes duplicate albums), so an in-place library never loses the very files
    the import that follows will read. Each row is removed before its file, so a failed deletion can never
    leave a row pointing at a deleted file. Album art follows the same rule. Empty directories are pruned
    with beets' `clutter` setting, as `beet remove -d` does.
    """
    entry = _load_entry(lib, target)
    if entry is None:
        raise CleanSlateError("not_found", f"No beets {target.subject} with id {target.beets_id}.")
    plan = _deletion_plan(lib, entry, _normalized_source(source_path))
    to_delete = set(plan.to_delete)
    item_ids = [saved_id(item) for item in entry.items]
    for item in entry.items:
        item.remove(delete=item.path in to_delete, with_album=False)
    if entry.album is not None:
        entry.album.remove(delete=False, with_items=False)
        if plan.art is not None:
            remove_file(plan.art)
            prune_dirs(os.path.dirname(plan.art), lib.directory, clutter=beets_config["clutter"].as_str_seq())
    removed = RemovedEntry(
        target=target,
        item_ids=item_ids,
        deleted_paths=[displayable_path(path) for path in plan.to_delete],
        kept_paths=[displayable_path(path) for path in plan.kept],
        deleted_art=displayable_path(plan.art) if plan.art else None,
    )
    narrate(
        f"Removed {target.subject} '{entry.label}' (#{target.beets_id}) from the library: {len(item_ids)} row(s), "
        f"{len(removed.deleted_paths)} file(s) deleted"
        + (", album art deleted" if removed.deleted_art else "")
        + (f", {len(removed.kept_paths)} file(s) outside the library left alone" if removed.kept_paths else "")
        + "."
    )
    return removed


def _load_entry(lib: Library, target: CleanSlateTarget) -> _Entry | None:
    if target.subject == "album":
        album = lib.get_album(target.beets_id)
        if album is None:
            return None
        return _Entry(
            label=f"{album.albumartist or '?'} - {album.album or '?'}", album=album, items=list(album.items())
        )
    item = lib.get_item(target.beets_id)
    if item is None:
        return None
    return _Entry(label=f"{item.artist or '?'} - {item.title or '?'}", album=None, items=[item])


def _models(entry: _Entry) -> list[LibModel]:
    return [entry.album, *entry.items] if entry.album is not None else [*entry.items]


def _flexible_attributes(entry: _Entry, *, excluding: Collection[str] = ()) -> list[str]:
    names = {name for model in _models(entry) for name in model._values_flex}
    return sorted(names.difference(excluding))


def _preserved_fields(entry: _Entry, names: Collection[str]) -> dict[str, str]:
    """
    The entry's values for the flexible attributes in `names`: the album's, else the first item's holding one.

    A field counts as held when its value is neither None nor blank, as in `DownloaderHook.query_params`. Fixed
    fields never qualify; the fresh import derives those itself.
    """
    preserved: dict[str, str] = {}
    for name in names:
        for model in _models(entry):
            value = model._values_flex.get(name)
            if value is not None and str(value).strip():
                preserved[name] = str(value)
                break
    return preserved


def _normalized_source(source_path: str) -> bytes:
    return normpath(os.path.realpath(os.path.expanduser(source_path)))


def _inside(path: bytes, root: bytes) -> bool:
    return path == root or root in ancestry(path)


def _deletion_plan(lib: Library, entry: _Entry, source: bytes) -> _DeletionPlan:
    to_delete: list[bytes] = []
    kept: list[bytes] = []
    for item in entry.items:
        if not file_exists(item):
            continue
        path = normpath(item.path)
        if _inside(path, lib.directory) and not _inside(path, source):
            to_delete.append(item.path)
        else:
            kept.append(item.path)
    art: bytes | None = None
    if entry.album is not None and entry.album.artpath and os.path.exists(syspath(entry.album.artpath)):
        art_path = normpath(entry.album.artpath)
        if _inside(art_path, lib.directory) and not _inside(art_path, source):
            art = entry.album.artpath
    return _DeletionPlan(to_delete=to_delete, kept=kept, art=art)


def _scan_source(lib: Library, target: CleanSlateTarget, source: bytes, downloads_path: Path) -> _SourceScan:
    errors: list[str] = []
    shown = displayable_path(source)
    if not os.path.exists(syspath(source)):
        return _SourceScan([f"Source path '{shown}' does not exist."], 0, 0, None)
    downloads_root = normpath(os.path.realpath(os.path.expanduser(str(downloads_path))))
    if source == downloads_root or not _inside(source, downloads_root):
        errors.append(f"Source path must be a folder inside '{displayable_path(downloads_root)}'.")
    if _inside(source, lib.directory):
        errors.append("Source path lies inside the beets library directory; a clean slate imports from outside it.")
    is_dir = os.path.isdir(syspath(source))
    if target.subject == "album" and not is_dir:
        errors.append("Source path must be a folder for an album.")
    if errors:
        return _SourceScan(errors, 0, 0, None)

    groups = list(albums_in_dir(source)) if is_dir else [([source], [source])]
    readable: list[Item] = []
    for _dirs, files in groups:
        readable.extend(_readable_items(files))
    audio_files = len(readable)
    if audio_files == 0:
        errors.append(f"No readable audio files found under '{shown}'.")
    elif target.subject == "album" and len(groups) != 1:
        errors.append(f"'{shown}' holds {len(groups)} album folders; point at the album's own folder.")
    elif target.subject == "track" and audio_files != 1:
        errors.append(f"'{shown}' holds {audio_files} audio files; a standalone track needs exactly one.")
    common = Counter((item.albumartist or item.artist or "", item.album or "") for item in readable).most_common(1)
    return _SourceScan(errors, audio_files, len(groups), common[0][0] if common else None)


def _readable_items(paths: Iterable[bytes]) -> list[Item]:
    items: list[Item] = []
    for path in paths:
        try:
            items.append(Item.from_path(bytestring_path(path)))
        except ReadError:
            continue
    return items
