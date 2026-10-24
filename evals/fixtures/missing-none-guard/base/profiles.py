"""User profiles as stored by the accounts service."""


def load_profile(store, user_id):
    """Return the user's profile dict, or None if they never filled one in."""
    return store.get("profiles", {}).get(user_id)
