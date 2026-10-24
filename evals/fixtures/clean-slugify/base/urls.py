"""URL building helpers."""

from urllib.parse import quote


def path_join(*parts):
    """Join path segments with single slashes, percent-encoding each segment."""
    return "/" + "/".join(quote(p.strip("/"), safe="") for p in parts if p.strip("/"))
