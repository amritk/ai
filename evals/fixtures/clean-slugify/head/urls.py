"""URL building helpers."""

import re
import unicodedata
from urllib.parse import quote


def path_join(*parts):
    """Join path segments with single slashes, percent-encoding each segment."""
    return "/" + "/".join(quote(p.strip("/"), safe="") for p in parts if p.strip("/"))


def slugify(title, max_length=60):
    """Lowercase ASCII slug of `title`: words joined by "-", at most `max_length` chars.

    Returns "" when `title` has no ASCII letters or digits; callers fall back to
    the record's id in that case.
    """
    if max_length < 1:
        raise ValueError("max_length must be >= 1")
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug[:max_length].rstrip("-")
