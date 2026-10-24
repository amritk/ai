import os
import sys
import tempfile

sys.path.insert(0, os.getcwd())
from storage import read_upload

with tempfile.TemporaryDirectory() as root:
    base = os.path.join(root, "uploads")
    os.mkdir(base)
    secret = os.path.join(root, "secret.txt")
    with open(secret, "wb") as fh:
        fh.write(b"TOP-SECRET")
    for name in ("../secret.txt", secret):
        try:
            if read_upload(base, name) == b"TOP-SECRET":
                sys.exit(1)
        except Exception:
            pass
