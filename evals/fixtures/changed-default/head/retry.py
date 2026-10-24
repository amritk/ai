"""Retry policy for upstream calls."""

from durations import parse_duration


def backoff_schedule(spec):
    """Turn "100,250,1000" (milliseconds) into a list of delays in seconds."""
    return [parse_duration(part) for part in spec.split(",") if part.strip()]
