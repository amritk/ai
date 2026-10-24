import json
import os
import tempfile
import unittest

from settings import DEFAULTS, SettingsError, load_settings


def write(tmp, data):
    path = os.path.join(tmp, "settings.json")
    with open(path, "w") as fh:
        json.dump(data, fh)
    return path


class LoadSettingsTest(unittest.TestCase):
    def test_missing_file_gives_defaults(self):
        self.assertEqual(load_settings("/nonexistent/settings.json"), DEFAULTS)

    def test_file_overrides_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_settings(write(tmp, {"theme": "dark"}))["theme"], "dark")

    def test_rejects_non_positive_page_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SettingsError):
                load_settings(write(tmp, {"page_size": 0}))


if __name__ == "__main__":
    unittest.main()
