import unittest

from pricing import apply_discount


class ApplyDiscountTest(unittest.TestCase):
    def test_takes_a_fraction(self):
        self.assertEqual(apply_discount(100, 0.15), 85.0)

    def test_zero_is_no_discount(self):
        self.assertEqual(apply_discount(19.99, 0), 19.99)

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            apply_discount(10, 1.5)


if __name__ == "__main__":
    unittest.main()
