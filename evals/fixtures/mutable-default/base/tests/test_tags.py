import unittest

from tags import normalize_tag


class NormalizeTagTest(unittest.TestCase):
    def test_normalizes(self):
        self.assertEqual(normalize_tag(" Big Idea "), "big-idea")


if __name__ == "__main__":
    unittest.main()
