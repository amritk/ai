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


def truncate_words(text, max_words):
    """Keep the first `max_words` words of `text`, ending in "…" when any were dropped.

    Text that already fits is returned unchanged, whitespace included.
    """
    if max_words < 1:
        raise ValueError("max_words must be >= 1")
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"
