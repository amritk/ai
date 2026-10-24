"""Small text helpers."""


def word_count(text):
    return len(text.split())


def truncate(text, limit):
    """Cut `text` to at most `limit` characters, ending in "…" when anything was cut."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
