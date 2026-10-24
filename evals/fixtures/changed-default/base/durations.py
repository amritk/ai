"""Parse human-written durations like "30", "5m", "2h"."""

_UNITS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}


def parse_duration(text):
    """Return the duration in seconds. A bare number is seconds."""
    text = text.strip()
    for suffix in sorted(_UNITS, key=len, reverse=True):
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * _UNITS[suffix]
    return float(text)
