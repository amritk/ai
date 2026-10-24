import os
import tempfile
import unittest

from storage import read_upload, save_upload


class SaveUploadTest(unittest.TestCase):
    def test_strips_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = save_upload(tmp, "../../evil.txt", b"x")
            self.assertEqual(os.path.dirname(path), tmp)


class ReadUploadTest(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_upload(tmp, "a.txt", b"hello")
            self.assertEqual(read_upload(tmp, "a.txt"), b"hello")


if __name__ == "__main__":
    unittest.main()
