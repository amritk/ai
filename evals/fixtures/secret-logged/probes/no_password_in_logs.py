import io
import logging
import os
import sys

sys.path.insert(0, os.getcwd())
from auth import hash_password, login

stream = io.StringIO()
handler = logging.StreamHandler(stream)
root = logging.getLogger()
root.addHandler(handler)
root.setLevel(logging.DEBUG)
users = {"ann": {"salt": b"salt", "hash": hash_password("pw", b"salt")}}
login(users, "ann", "hunter2-wrong")
sys.exit(1 if "hunter2-wrong" in stream.getvalue() else 0)
