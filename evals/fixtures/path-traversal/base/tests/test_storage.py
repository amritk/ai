import os
import tempfile
import unittest

from storage import save_upload


class SaveUploadTest(unittest.TestCase):
    def test_strips_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = save_upload(tmp, "../../evil.txt", b"x")
            self.assertEqual(os.path.dirname(path), tmp)


if __name__ == "__main__":
    unittest.main()
