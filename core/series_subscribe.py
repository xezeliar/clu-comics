"""Subscribing a series to a folder, and the folder it gets by default.

One body for the series page's Subscribe button and for setting up a reading
list's series in bulk (core/series_setup.py), so the two cannot drift apart:
the same sanitising, the same cvinfo and series.json, the same Monitor rule.
"""

import os
import re

from core.app_logging import app_logger
from core.database import get_series_by_id
from models import metron

DEFAULT_MOVE_PATTERN = "{publisher}/{series_name}/v{start_year}"


class SubscribeError(Exception):
    """A subscribe request that cannot be carried out; ``status`` is the HTTP code."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def clean_folder_path(path):
    """Sanitise every segment of a user-editable folder path.

    The path is handed straight to os.makedirs, so each segment goes through
    the one sanitiser (never the '/' separators). Mirrors sanitizePathSegment()
    in templates/series.html. Returns '' when nothing usable is left.
    """
    from helpers import sanitize_path_segment

    path = (path or "").strip()
    leading_slash = path.startswith("/")
    segments = [sanitize_path_segment(seg) for seg in path.split("/")]
    segments = [seg for seg in segments if seg]
    path = ("/" if leading_slash else "") + "/".join(segments)
    return "" if path == "/" else path


def build_subscribe_path(series, library_path, pattern=None):
    """The folder the Subscribe dialog proposes for a series.

    The Python twin of buildSubscribePath() in templates/series.html, used
    where no dialog runs (bulk setup). Same tokens, same global replacement
    (#616), same clean-up of tokens without a value.
    """
    from helpers import sanitize_path_segment

    def field(key):
        if isinstance(series, dict):
            return series.get(key)
        return getattr(series, key, None)

    publisher = field("publisher_name")
    if not publisher:
        pub = field("publisher")
        if isinstance(pub, dict):
            publisher = pub.get("name")
        elif pub is not None:
            publisher = getattr(pub, "name", None)

    values = {
        "publisher": sanitize_path_segment(publisher or "Unknown").strip(),
        "series_name": sanitize_path_segment(field("name") or "Unknown").strip(),
        "start_year": str(field("year_began") or field("volume_year") or ""),
    }
    volume = field("volume") or field("volume_number")
    values["volume_number"] = f"v{volume}" if volume else ""

    path = pattern or DEFAULT_MOVE_PATTERN
    for token, value in values.items():
        path = path.replace("{" + token + "}", value)

    path = re.sub(r"\{[A-Za-z_][^}]*\}", "", path)  # tokens with no value
    path = re.sub(r"\s*\(\s*\)", "", path)
    path = re.sub(r"\s*\[\s*\]", "", path)
    path = re.sub(r"\s+", " ", path).strip()
    path = re.sub(r"/+", "/", path)

    base = (library_path or "").rstrip("/")
    return base + "/" + path.lstrip("/")


def subscribe_series(series_id, path, monitored=True):
    """Create the folder, map the series to it, write cvinfo and series.json.

    The series must already be in the local database (the series page caches
    it on view; bulk setup caches it first). ``monitored=False`` creates it as
    Not monitored and locks that choice, so nothing is searched in between and
    core.auto_monitor never changes it. Returns the folder actually used.
    Raises SubscribeError for a bad request.
    """
    from core.database import save_series_mapping

    path = clean_folder_path(path)
    if not path:
        raise SubscribeError("Path required", 400)

    series = get_series_by_id(series_id)
    if not series:
        raise SubscribeError("Series not found", 404)

    os.makedirs(path, exist_ok=True)
    app_logger.info(f"Created folder for subscription: {path}")

    save_series_mapping(series, path)
    app_logger.info(f"Subscribed series {series_id} to {path}")

    if not monitored:
        from core.database import set_series_monitored

        set_series_monitored(series_id, False, lock=True)

    # Background: pre-populate the GetComics scrape index for this series
    # so we're ready for searches without hitting GetComics live
    from models.getcomics import prepopulate_series_index

    series_name = series.get("name", "")
    if series_name:
        prepopulate_series_index(series_name)

    # Create cvinfo file with available metadata
    cv_id = series.get("cv_id")
    metron_id = series.get("id") or series_id
    cvinfo_path = os.path.join(path, "cvinfo")

    # Use metron.create_cvinfo_file to properly handle missing cv_id
    success = metron.create_cvinfo_file(
        cvinfo_path,
        cv_id=cv_id,  # Pass None if cv_id is missing
        series_id=metron_id,
        publisher_name=series.get("publisher_name"),
        start_year=series.get("year_began"),
    )

    if success:
        if not cv_id:
            app_logger.warning(
                f"Created cvinfo without ComicVine ID for series {series_id} at {cvinfo_path}"
            )
        else:
            app_logger.info(f"Created cvinfo at {cvinfo_path} with CV ID {cv_id}")
    else:
        app_logger.error(f"Failed to create cvinfo at {cvinfo_path}")

    from models.series_json import write_series_json
    from core.series_json_builder import with_description_fallback

    write_series_json(
        path, with_description_fallback(series, path), api=metron.get_flask_api()
    )

    return path
