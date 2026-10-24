import unittest

from auth import hash_password, login, verify

USERS = {"ann": {"salt": b"salt", "hash": hash_password("pw", b"salt")}}


class VerifyTest(unittest.TestCase):
    def test_accepts_the_right_password(self):
        self.assertTrue(verify("pw", b"salt", hash_password("pw", b"salt")))

    def test_rejects_a_wrong_password(self):
        self.assertFalse(verify("nope", b"salt", hash_password("pw", b"salt")))


class LoginTest(unittest.TestCase):
    def test_known_user(self):
        self.assertTrue(login(USERS, "ann", "pw"))

    def test_unknown_user(self):
        self.assertFalse(login(USERS, "bob", "pw"))


if __name__ == "__main__":
    unittest.main()
