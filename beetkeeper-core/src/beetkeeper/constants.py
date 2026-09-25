"""
The shared beets listener event-type vocabulary, used by both the API models and the database models.

This lives outside `beetkeeper.api` because importing anything under that package pulls in the whole
FastAPI app (via `beetkeeper.api.__init__`), whose routers import `beetkeeper.db.models` — so the db
layer must get the enum from a neutral home to avoid a circular import.
"""

from enum import StrEnum, unique


@unique
class BeetsEventType(StrEnum):
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
