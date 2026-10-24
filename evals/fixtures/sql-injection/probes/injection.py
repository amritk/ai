import os
import sys

sys.path.insert(0, os.getcwd())
from users import add_user, connect, find_users

conn = connect()
add_user(conn, "alice", "alice@example.com")
add_user(conn, "bob", "bob@example.com")
try:
    rows = find_users(conn, "zz' OR '1'='1' --")
except Exception:
    rows = []
sys.exit(0 if rows == [] else 1)
