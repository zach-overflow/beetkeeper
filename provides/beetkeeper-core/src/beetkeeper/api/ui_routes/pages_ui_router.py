"""Full-page HTML routes. Each renders a `page_templates/*.html` that extends `base_template.html`."""

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from beetkeeper.api.api_models.import_api_models import (
    import_config_flag,
    import_config_logpath,
    import_config_set_fields,
)
from beetkeeper.api.dependencies import BeetsLibraryDep, UserConfigDep
from beetkeeper.api.jinja_driver import get_templates

pages_ui_router = APIRouter()


@pages_ui_router.get("/")
async def default_page() -> RedirectResponse:
    """Send the site root to the search page, the UI's landing page."""
    return RedirectResponse(url="/search", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@pages_ui_router.get("/events", response_class=HTMLResponse)
async def events_page(request: Request) -> HTMLResponse:
    """Render the beets events page; its table loads through the `/fragment/event` HTMX fragment."""
    return get_templates().TemplateResponse(request=request, name="page_templates/events_page.html", context={})


@pages_ui_router.get("/import", response_class=HTMLResponse)
async def import_page(
    request: Request,
    library: BeetsLibraryDep,
    user_config: UserConfigDep,
    path: str = "",
    clean_slate_album_id: int | None = None,
    clean_slate_item_id: int | None = None,
    clean_slate_source: str = "",
) -> HTMLResponse:
    """
    The import page. The form's option controls are prefilled from the beets config's `import` section,
    so submitting the untouched form matches a plain `beet import` (and any change is an explicit override).

    `path` prefills the import form; `clean_slate_album_id` (or `clean_slate_item_id`) plus
    `clean_slate_source` prefill the clean-slate form, so the search page can link straight to
    "import from here" / "clean-slate this entry".
    """
    logpath = import_config_logpath()
    import_defaults = {
        "quiet": import_config_flag("quiet"),
        "group_albums": import_config_flag("group_albums"),
        "flat": import_config_flag("flat"),
        "logpath": str(logpath) if logpath is not None else "",
        "set_fields": "\n".join(f"{key}={value}" for key, value in import_config_set_fields().items()),
    }
    context = {
        "import_defaults": import_defaults,
        "import_path": path,
        "downloads_path": str(user_config.downloads_path),
        "clean_slate": await _clean_slate_prefill(
            library, clean_slate_album_id, clean_slate_item_id, clean_slate_source
        ),
    }
    return get_templates().TemplateResponse(request=request, name="page_templates/import_page.html", context=context)


async def _clean_slate_prefill(
    library: BeetsLibraryDep, album_id: int | None, item_id: int | None, source: str
) -> dict[str, Any] | None:
    """The clean-slate form's prefill (entry label + ids + source), or None when no entry was linked to."""
    if album_id is not None:
        album = (await library.get_albums([album_id])).get(album_id)
        label = f"{album['albumartist'] or '?'} - {album['album'] or '?'}" if album else "(album not found)"
        return {"subject": "album", "beets_id": album_id, "label": label, "source": source}
    if item_id is not None:
        track = (await library.get_tracks([item_id])).get(item_id)
        label = f"{track['artist'] or '?'} - {track['title'] or '?'}" if track else "(track not found)"
        return {"subject": "track", "beets_id": item_id, "label": label, "source": source}
    return None


@pages_ui_router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request) -> HTMLResponse:
    """
    UI for the read-only `query_router` endpoints: search (list), library stats, and field reference.

    The page is static shell; its data loads via the `search_ui_fragments_router` HTMX fragments.
    """
    return get_templates().TemplateResponse(request=request, name="page_templates/search_page.html", context={})
