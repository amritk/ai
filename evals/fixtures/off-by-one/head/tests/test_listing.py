import unittest

from listing import page_count, paginate


class PageCountTest(unittest.TestCase):
    def test_rounds_up(self):
        self.assertEqual(page_count(10, 3), 4)

    def test_empty_is_one_page(self):
        self.assertEqual(page_count(0, 3), 1)


class PaginateTest(unittest.TestCase):
    def test_rejects_page_zero(self):
        with self.assertRaises(ValueError):
            paginate([1, 2, 3], 0, 2)


if __name__ == "__main__":
    unittest.main()
