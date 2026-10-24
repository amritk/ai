"""User lookups backed by sqlite."""

import sqlite3


def connect(path=":memory:"):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    return conn


def add_user(conn, name, email):
    cur = conn.execute("INSERT INTO users (name, email) VALUES (?, ?)", (name, email))
    return cur.lastrowid


def get_user(conn, user_id):
    row = conn.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
    return None if row is None else {"id": row[0], "name": row[1], "email": row[2]}
