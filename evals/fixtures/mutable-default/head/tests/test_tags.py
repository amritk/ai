import unittest

from tags import normalize_tag, with_tag


class NormalizeTagTest(unittest.TestCase):
    def test_normalizes(self):
        self.assertEqual(normalize_tag(" Big Idea "), "big-idea")


class WithTagTest(unittest.TestCase):
    def test_skips_duplicates(self):
        self.assertEqual(with_tag("Draft", ["draft"]), ["draft"])


if __name__ == "__main__":
    unittest.main()
