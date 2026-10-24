"""Runtime settings read from environment variables."""

import os

from durations import parse_duration


def request_timeout():
    """Seconds to wait on an upstream request. Defaults to 30 seconds."""
    return parse_duration(os.environ.get("REQUEST_TIMEOUT", "30"))
