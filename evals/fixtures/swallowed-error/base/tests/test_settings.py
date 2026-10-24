import json
import os
import tempfile
import unittest

from settings import DEFAULTS, load_settings


class LoadSettingsTest(unittest.TestCase):
    def test_missing_file_gives_defaults(self):
        self.assertEqual(load_settings("/nonexistent/settings.json"), DEFAULTS)

    def test_file_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "settings.json")
            with open(path, "w") as fh:
                json.dump({"theme": "dark"}, fh)
            self.assertEqual(load_settings(path)["theme"], "dark")


if __name__ == "__main__":
    unittest.main()
