import unittest

from profiles import load_profile


class LoadProfileTest(unittest.TestCase):
    def test_missing_profile_is_none(self):
        self.assertIsNone(load_profile({}, 1))


if __name__ == "__main__":
    unittest.main()
