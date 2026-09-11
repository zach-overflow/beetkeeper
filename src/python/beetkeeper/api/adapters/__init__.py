"""Logic bridging the FastAPI route handlers and the underlying `beetkeeper` database and core code."""

from beetkeeper.api.adapters.events_adapters import (
    listener_event_lookup_by_type_and_id,
    listener_event_records_lookup,
    merge_import_event_records,
)
from beetkeeper.api.adapters.search_adapters import import_source_paths_by_album_id, import_source_paths_by_track_id

__all__ = [
    "import_source_paths_by_album_id",
    "import_source_paths_by_track_id",
    "listener_event_lookup_by_type_and_id",
    "listener_event_records_lookup",
    "merge_import_event_records",
]
