"""Define any custom FastAPI request or response pydantic models for the `/api/events` subrouter here."""

from enum import StrEnum, unique

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


@unique
class APIEventType(StrEnum):
    """
    Subset of beets listener `event_type`s which the API accepts from our plugin client.
    See also:
        https://beets.readthedocs.io/en/stable/dev/plugins/events.html
    """

    ALBUM_IMPORTED = "album_imported"
    ALBUM_REMOVED = "album_removed"
    IMPORT_TASK_FILES = "import_task_files"
    TRACK_IMPORTED = "item_imported"
    TRACK_REMOVED = "item_removed"


class _BaseEventResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: APIEventType


class EventIngestResponse(_BaseEventResponse):
    ingested_id: int | None = Field(
        default=None, description="The beets db ID of the processed album / item, if successful."
    )
    error_msg: str | None = Field(None, description="Error message to return to the client, if any.")


class MultiItemEventIngestResponse(_BaseEventResponse):
    event_ingest_responses: list[EventIngestResponse] = Field(default_factory=list)


class _BaseEventBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    event_type: APIEventType
    pushed_at: AwareDatetime


class AlbumEventBody(_BaseEventBody):
    """
    A post request payload expected from the plugin's listener for the `beetsplug.beetkeeper_plugin.event_listener`
    client's `album_imported` event pushes.
    """

    album_fields: APIAlbum


class TrackEventBody(AlbumEventBody):
    """
    A post request payload expected from the plugin's listener for the `beetsplug.beetkeeper_plugin.event_listener`
    client's `item_imported` (track imported) event pushes.
    """

    track_fields: APITrack


# TODO[later]: add submodels corresponding to relevant parts of the following beets event models:
#  `beets.importer.ImportSession`, `beets.importer.ImportTask`, `beets.autotag.AlbumMatch`


class ImportTaskFilesEventBody(_BaseEventBody):
    choice_flag: str | None
    imported_items: list[TrackEventBody]


class APIAlbum(BaseModel):
    """
    Model for the relevant parts of a `beets.library.Album` instance. used during beets plugin client push events
    for an event tied to a given album. For simplicity, we only mark `id` as required, with all other fields as
    optional (which might not be the case for beets internals).

    NOTE: This was generated from `build_scripts/code_gen/pydantic_field_info_from_beets_model.py`.
    """

    id: int
    added: float | None = Field(default=None)
    album: str = Field(default="")
    albumartist: str = Field(default="")
    albumartist_credit: str = Field(default="")
    albumartist_sort: str = Field(default="")
    albumartists: list | None = Field(default=None)
    albumartists_credit: list | None = Field(default=None)
    albumartists_sort: list | None = Field(default=None)
    albumdisambig: str = Field(default="")
    albumstatus: str = Field(default="")
    albumtype: str = Field(default="")
    albumtypes: list | None = Field(default=None)
    artpath: bytes = Field(default=b"")
    asin: str = Field(default="")
    barcode: str = Field(default="")
    catalognum: str = Field(default="")
    comp: bool = Field(default=False)
    country: str = Field(default="")
    day: int | None = Field(default=None)
    discogs_albumid: int | None = Field(default=None)
    discogs_artistid: int | None = Field(default=None)
    discogs_labelid: int | None = Field(default=None)
    disctotal: int | None = Field(default=None)
    genres: list | None = Field(default=None)
    label: str = Field(default="")
    language: str = Field(default="")
    mb_albumartistid: str = Field(default="")
    mb_albumartistids: list | None = Field(default=None)
    mb_albumid: str = Field(default="")
    mb_releasegroupid: str = Field(default="")
    month: int | None = Field(default=None)
    original_day: int | None = Field(default=None)
    original_month: int | None = Field(default=None)
    original_year: int | None = Field(default=None)
    r128_album_gain: float | None = Field(default=None)
    release_group_title: str = Field(default="")
    releasegroupdisambig: str = Field(default="")
    rg_album_gain: float | None = Field(default=None)
    rg_album_peak: float | None = Field(default=None)
    script: str = Field(default="")
    style: str = Field(default="")
    year: int | None = Field(default=None)


class APITrack(BaseModel):
    """
    Model for the relevant parts of a `beets.library.Item` (track) instance. used during beets plugin client push events
    for an event tied to a single track ('Item'). For simplicity, we only mark `id` as required, with all other fields as
    optional (which might not be the case for beets internals).

    NOTE: This was generated from `build_scripts/code_gen/pydantic_field_info_from_beets_model.py`.
    """

    id: int
    acoustid_fingerprint: str = Field(default="")
    acoustid_id: str = Field(default="")
    added: float | None = Field(default=None)
    album: str = Field(default="")
    album_id: int | None = Field(default=None)
    albumartist: str = Field(default="")
    albumartist_credit: str = Field(default="")
    albumartist_sort: str = Field(default="")
    albumartists: list | None = Field(default=None)
    albumartists_credit: list | None = Field(default=None)
    albumartists_sort: list | None = Field(default=None)
    albumdisambig: str = Field(default="")
    albumstatus: str = Field(default="")
    albumtype: str = Field(default="")
    albumtypes: list | None = Field(default=None)
    arrangers: list | None = Field(default=None)
    arrangers_ids: list | None = Field(default=None)
    artist: str = Field(default="")
    artist_credit: str = Field(default="")
    artist_sort: str = Field(default="")
    artists: list | None = Field(default=None)
    artists_credit: list | None = Field(default=None)
    artists_ids: list | None = Field(default=None)
    artists_sort: list | None = Field(default=None)
    asin: str = Field(default="")
    barcode: str = Field(default="")
    bitdepth: int | None = Field(default=None)
    bitrate: int | None = Field(default=None)
    bitrate_mode: str = Field(default="")
    bpm: int | None = Field(default=None)
    catalognum: str = Field(default="")
    channels: int | None = Field(default=None)
    comments: str = Field(default="")
    comp: bool = Field(default=False)
    composer_sort: str = Field(default="")
    composers: list | None = Field(default=None)
    composers_ids: list | None = Field(default=None)
    country: str = Field(default="")
    day: int | None = Field(default=None)
    disc: int | None = Field(default=None)
    discogs_albumid: int | None = Field(default=None)
    discogs_artistid: int | None = Field(default=None)
    discogs_labelid: int | None = Field(default=None)
    disctitle: str = Field(default="")
    disctotal: int | None = Field(default=None)
    encoder: str = Field(default="")
    encoder_info: str = Field(default="")
    encoder_settings: str = Field(default="")
    format: str = Field(default="")
    genres: list | None = Field(default=None)
    grouping: str = Field(default="")
    initial_key: str = Field(default="")
    isrc: str = Field(default="")
    label: str = Field(default="")
    language: str = Field(default="")
    length: float | None = Field(default=None)
    lyricists: list | None = Field(default=None)
    lyricists_ids: list | None = Field(default=None)
    lyrics: str = Field(default="")
    mb_albumartistid: str = Field(default="")
    mb_albumartistids: list | None = Field(default=None)
    mb_albumid: str = Field(default="")
    mb_artistid: str = Field(default="")
    mb_artistids: list | None = Field(default=None)
    mb_releasegroupid: str = Field(default="")
    mb_releasetrackid: str = Field(default="")
    mb_trackid: str = Field(default="")
    mb_workid: str = Field(default="")
    media: str = Field(default="")
    month: int | None = Field(default=None)
    mtime: float | None = Field(default=None)
    original_day: int | None = Field(default=None)
    original_month: int | None = Field(default=None)
    original_year: int | None = Field(default=None)
    path: bytes = Field(default=b"")
    r128_album_gain: float | None = Field(default=None)
    r128_track_gain: float | None = Field(default=None)
    release_group_title: str = Field(default="")
    releasegroupdisambig: str = Field(default="")
    remixers: list | None = Field(default=None)
    remixers_ids: list | None = Field(default=None)
    rg_album_gain: float | None = Field(default=None)
    rg_album_peak: float | None = Field(default=None)
    rg_track_gain: float | None = Field(default=None)
    rg_track_peak: float | None = Field(default=None)
    samplerate: int | None = Field(default=None)
    script: str = Field(default="")
    style: str = Field(default="")
    subtitle: str = Field(default="")
    title: str = Field(default="")
    track: int | None = Field(default=None)
    trackdisambig: str = Field(default="")
    tracktotal: int | None = Field(default=None)
    work: str = Field(default="")
    work_disambig: str = Field(default="")
    year: int | None = Field(default=None)
