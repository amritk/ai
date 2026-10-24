"""Tag bookkeeping for notes."""


def normalize_tag(tag):
    """Lowercase, trimmed, spaces as hyphens: " Big Idea " -> "big-idea"."""
    return tag.strip().lower().replace(" ", "-")


def with_tag(tag, tags=[]):
    """Return `tags` plus the normalized `tag`, without duplicates."""
    tag = normalize_tag(tag)
    if tag not in tags:
        tags.append(tag)
    return tags
