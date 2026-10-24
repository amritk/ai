"""Tag bookkeeping for notes."""


def normalize_tag(tag):
    """Lowercase, trimmed, spaces as hyphens: " Big Idea " -> "big-idea"."""
    return tag.strip().lower().replace(" ", "-")
