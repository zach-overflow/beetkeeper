"""Define any custom FastAPI request or response pydantic models for the `/api/events` subrouter here."""
from functools import cache
from typing import Any, Literal, Union
from pydantic import create_model

from beets.library import Album, Item


type _BeetModelFieldInfo = tuple[Union[Any | None], bool | bytes | str | None]


@cache
def _beets_lib_model_to_pydantic_field_info() -> dict[Literal["album", "track"], dict[str, _BeetModelFieldInfo]]:
    """
    Auto-generates a dict consumable by `pydantic.create_model` to allow for dynamically creating a
    `pydantic.BaseModel` subclass def for modelling beets' internal DB models of albums
    and tracks ('Items'). For simplicity, these models mark the `id` field as required, while setting all other
    fields as optional (which might not be the case for beets internals).
    Returns:
        dict of the form: {
            "album": <pydantic.model_create input for `beets.library.Album`>,
            "track": <pydantic.model_create input for `beets.library.Item`>,
        }
    """
    from beets.library import Album, Item
    from beets.library.fields import TYPE_BY_FIELD
    py_type_to_pydantic_default = {
        bool: False,
        bytes: bytes("", encoding="utf-8"),
        float: None,
        int: None,
        list: None,
        str: "",
    }
    beet_field_to_pytype = {
        beet_field: beets_type.model_type
        for beet_field, beets_type in TYPE_BY_FIELD.items() if beet_field != "id"
    }

    def _get_pyd_field_info(beets_model_type: type[Album | Item]) -> dict[str, _BeetModelFieldInfo]:
        """
        Returns a dict of field name to tuples of the type annotation, and default value for the given beets model
        field name.
        """
        res = {"id": (int, ...)}  # Use ... (Ellipsis) to indicate that a field is required
        for field_name in sorted(beets_model_type._field_names):
            if field_name == "id":
                continue
            py_type = beet_field_to_pytype[field_name]
            default_field_value = py_type_to_pydantic_default[py_type]
            res[field_name] = (py_type, default_field_value)
        return res

    # Define fields as dict mapping field name to (field_type, field_default_value) tuples
    return {
        "album": _get_pyd_field_info(beets_model_type=Album),
        "track": _get_pyd_field_info(beets_model_type=Item),
    }


# Dynamically generate the API pydantic submodels for Album and Track, from beets' model definitions.
BeetsAlbum = create_model("BeetsAlbum", **_beets_lib_model_to_pydantic_field_info()["album"])
BeetsTrack = create_model("BeetsTrack", **_beets_lib_model_to_pydantic_field_info()["track"])
# TODO[later]: add submodels corresponding to relevant parts of the following beets event models:
#  `beets.importer.ImportSession`, `beets.importer.ImportTask`, `beets.autotag.AlbumMatch`


{'id': (int, Ellipsis),
 'added': (float, None),
 'album': (str, ''),
 'albumartist': (str, ''),
 'albumartist_credit': (str, ''),
 'albumartist_sort': (str, ''),
 'albumartists': (list, None),
 'albumartists_credit': (list, None),
 'albumartists_sort': (list, None),
 'albumdisambig': (str, ''),
 'albumstatus': (str, ''),
 'albumtype': (str, ''),
 'albumtypes': (list, None),
 'artpath': (bytes, b''),
 'asin': (str, ''),
 'barcode': (str, ''),
 'catalognum': (str, ''),
 'comp': (bool, False),
 'country': (str, ''),
 'day': (int, None),
 'discogs_albumid': (int, None),
 'discogs_artistid': (int, None),
 'discogs_labelid': (int, None),
 'disctotal': (int, None),
 'genres': (list, None),
 'label': (str, ''),
 'language': (str, ''),
 'mb_albumartistid': (str, ''),
 'mb_albumartistids': (list, None),
 'mb_albumid': (str, ''),
 'mb_releasegroupid': (str, ''),
 'month': (int, None),
 'original_day': (int, None),
 'original_month': (int, None),
 'original_year': (int, None),
 'r128_album_gain': (float, None),
 'release_group_title': (str, ''),
 'releasegroupdisambig': (str, ''),
 'rg_album_gain': (float, None),
 'rg_album_peak': (float, None),
 'script': (str, ''),
 'style': (str, ''),
 'year': (int, None)}