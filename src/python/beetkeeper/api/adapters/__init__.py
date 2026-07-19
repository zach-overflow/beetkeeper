"""Logic bridging the FastAPI route handlers and the underlying `beetkeeper` database and core code."""

from beetkeeper.api.adapters.events_adapters import listener_event_lookup_by_type_and_id, listener_event_records_lookup

__all__ = ["listener_event_lookup_by_type_and_id", "listener_event_records_lookup"]
