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
