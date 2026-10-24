import unittest

from urls import path_join, slugify


class PathJoinTest(unittest.TestCase):
    def test_joins_and_encodes(self):
        self.assertEqual(path_join("/a/", "b c", ""), "/a/b%20c")


class SlugifyTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_strips_accents(self):
        self.assertEqual(slugify("Crème Brûlée"), "creme-brulee")

    def test_respects_max_length_without_trailing_hyphen(self):
        self.assertEqual(slugify("aaa bbb", max_length=4), "aaa")

    def test_no_ascii_gives_empty(self):
        self.assertEqual(slugify("日本語"), "")

    def test_rejects_zero_length(self):
        with self.assertRaises(ValueError):
            slugify("x", max_length=0)


if __name__ == "__main__":
    unittest.main()
