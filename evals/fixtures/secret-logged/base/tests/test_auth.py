import unittest

from auth import hash_password, verify


class VerifyTest(unittest.TestCase):
    def test_accepts_the_right_password(self):
        self.assertTrue(verify("pw", b"salt", hash_password("pw", b"salt")))

    def test_rejects_a_wrong_password(self):
        self.assertFalse(verify("nope", b"salt", hash_password("pw", b"salt")))


if __name__ == "__main__":
    unittest.main()
