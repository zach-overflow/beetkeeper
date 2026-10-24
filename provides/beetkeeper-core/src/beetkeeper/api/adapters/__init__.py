"""Logic bridging the FastAPI route handlers and the underlying `beetkeeper` database and core code."""

from beetkeeper.api.adapters.events_adapters import (
    listener_event_lookup_by_type_and_id,
    listener_event_records_lookup,
    merge_import_event_records,
)
from beetkeeper.api.adapters.hooks_adapters import (
    find_missing_source_path,
    inferred_source_paths,
    record_inferred_source_path,
)
from beetkeeper.api.adapters.import_adapters import clean_slate_preview, reject_unsafe_clean_slate, require_import_job
from beetkeeper.api.adapters.search_adapters import import_source_paths_by_album_id, import_source_paths_by_track_id

__all__ = [
    "clean_slate_preview",
    "find_missing_source_path",
    "import_source_paths_by_album_id",
    "import_source_paths_by_track_id",
    "inferred_source_paths",
    "listener_event_lookup_by_type_and_id",
    "listener_event_records_lookup",
    "merge_import_event_records",
    "record_inferred_source_path",
    "reject_unsafe_clean_slate",
    "require_import_job",
]
