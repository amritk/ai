"""Read the app's JSON settings file."""

import json

DEFAULTS = {"theme": "light", "page_size": 20}


class SettingsError(Exception):
    """The settings file exists but cannot be used."""


def load_settings(path):
    """Return DEFAULTS overlaid with the file at `path`.

    A missing file means "use the defaults". A file that exists but is not
    valid JSON raises SettingsError, so a typo never silently resets a user's
    settings.
    """
    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:
        return dict(DEFAULTS)
    settings = {**DEFAULTS, **data}
    if not isinstance(settings["page_size"], int) or settings["page_size"] < 1:
        raise SettingsError(f"{path}: page_size must be a positive integer")
    return settings
