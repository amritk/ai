import os
import sys

sys.path.insert(0, os.getcwd())
from users import add_user, connect, find_users

conn = connect()
add_user(conn, "alice", "alice@example.com")
add_user(conn, "bob", "bob@example.com")
sys.exit(0 if [u["name"] for u in find_users(conn, "al")] == ["alice"] else 1)
