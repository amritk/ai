"""How a user's name is shown in the UI."""

from profiles import load_profile


def display_name(store, user):
    """The user's nickname if they set one, else their account name."""
    profile = load_profile(store, user["id"])
    nickname = profile.get("nickname")
    return nickname or user["name"]
