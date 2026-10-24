"""Paged views over in-memory result lists."""

import math


def page_count(total, per_page):
    """Number of pages needed to show `total` items, at least 1."""
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    return max(1, math.ceil(total / per_page))
