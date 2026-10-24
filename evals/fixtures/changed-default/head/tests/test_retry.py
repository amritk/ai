import unittest

from retry import backoff_schedule


class BackoffScheduleTest(unittest.TestCase):
    def test_reads_milliseconds(self):
        self.assertEqual(backoff_schedule("100,250"), [0.1, 0.25])

    def test_ignores_empty_parts(self):
        self.assertEqual(backoff_schedule("100,,"), [0.1])


if __name__ == "__main__":
    unittest.main()
