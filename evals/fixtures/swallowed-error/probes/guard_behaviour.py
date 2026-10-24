import json
import os
import sys
import tempfile

sys.path.insert(0, os.getcwd())
from settings import DEFAULTS, SettingsError, load_settings

assert load_settings("/nonexistent/settings.json") == DEFAULTS
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "settings.json")
    with open(path, "w") as fh:
        json.dump({"page_size": 0}, fh)
    try:
        load_settings(path)
        sys.exit(1)
    except SettingsError:
        pass
    with open(path, "w") as fh:
        json.dump({"theme": "dark"}, fh)
    assert load_settings(path)["theme"] == "dark"
