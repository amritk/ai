import unittest

from durations import parse_duration


class ParseDurationTest(unittest.TestCase):
    def test_suffixes(self):
        self.assertEqual(parse_duration("5m"), 300)
        self.assertEqual(parse_duration("2h"), 7200)
        self.assertAlmostEqual(parse_duration("250ms"), 0.25)


if __name__ == "__main__":
    unittest.main()
