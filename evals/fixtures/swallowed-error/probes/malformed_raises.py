import os
import sys
import tempfile

sys.path.insert(0, os.getcwd())
from settings import SettingsError, load_settings

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "settings.json")
    with open(path, "w") as fh:
        fh.write('{"theme": "dark",}')
    try:
        load_settings(path)
    except SettingsError:
        sys.exit(0)
    except Exception:
        sys.exit(1)
sys.exit(1)
