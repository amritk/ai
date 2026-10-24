"""Paged views over in-memory result lists."""

import math


def page_count(total, per_page):
    """Number of pages needed to show `total` items, at least 1."""
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    return max(1, math.ceil(total / per_page))


def paginate(items, page, per_page):
    """Return page `page` of `items`. Pages are numbered from 1, like page_count."""
    if page < 1:
        raise ValueError("page must be >= 1")
    start = page * per_page
    return list(items[start : start + per_page])
