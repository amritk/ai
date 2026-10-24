import unittest

from text import truncate, truncate_words, word_count


class TextTest(unittest.TestCase):
    def test_word_count(self):
        self.assertEqual(word_count("  two   words "), 2)

    def test_truncate(self):
        self.assertEqual(truncate("abcdef", 4), "abc…")
        self.assertEqual(truncate("abc", 4), "abc")

    def test_truncate_rejects_zero(self):
        with self.assertRaises(ValueError):
            truncate("abc", 0)


class TruncateWordsTest(unittest.TestCase):
    def test_drops_extra_words(self):
        self.assertEqual(truncate_words("one two three", 2), "one two…")

    def test_text_that_fits_is_unchanged(self):
        self.assertEqual(truncate_words(" one  two ", 2), " one  two ")

    def test_empty_text(self):
        self.assertEqual(truncate_words("", 3), "")

    def test_rejects_zero(self):
        with self.assertRaises(ValueError):
            truncate_words("one", 0)


if __name__ == "__main__":
    unittest.main()
