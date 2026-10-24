import unittest

from text import truncate, word_count


class TextTest(unittest.TestCase):
    def test_word_count(self):
        self.assertEqual(word_count("  two   words "), 2)

    def test_truncate(self):
        self.assertEqual(truncate("abcdef", 4), "abc…")
        self.assertEqual(truncate("abc", 4), "abc")

    def test_truncate_rejects_zero(self):
        with self.assertRaises(ValueError):
            truncate("abc", 0)


if __name__ == "__main__":
    unittest.main()
