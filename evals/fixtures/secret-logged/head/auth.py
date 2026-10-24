"""Password checks against stored PBKDF2 hashes."""

import hashlib
import hmac
import logging

log = logging.getLogger(__name__)
_ITERATIONS = 100_000


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)


def verify(password, salt, expected):
    return hmac.compare_digest(hash_password(password, salt), expected)


def login(users, username, password):
    """Return True when `username` exists and `password` matches its hash."""
    record = users.get(username)
    if record is None:
        log.info("login failed: unknown user %s", username)
        return False
    ok = verify(password, record["salt"], record["hash"])
    if not ok:
        log.warning("login failed for %s with password %r", username, password)
    return ok
