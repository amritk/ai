import os
import sys
import tempfile

sys.path.insert(0, os.getcwd())
from storage import read_upload, save_upload

with tempfile.TemporaryDirectory() as tmp:
    save_upload(tmp, "a.txt", b"hello")
    sys.exit(0 if read_upload(tmp, "a.txt") == b"hello" else 1)
