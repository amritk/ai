import os
import sys

sys.path.insert(0, os.getcwd())
from auth import hash_password, login

users = {"ann": {"salt": b"salt", "hash": hash_password("pw", b"salt")}}
ok = login(users, "ann", "pw") is True and login(users, "ann", "x") is False and login(users, "bob", "pw") is False
sys.exit(0 if ok else 1)
