"""Price arithmetic. Discounts are fractions: 0.15 means 15%, matching the payments API."""


def apply_discount(price, rate):
    """Return `price` reduced by `rate` (a fraction between 0 and 1), rounded to cents."""
    if not 0 <= rate <= 1:
        raise ValueError("rate must be between 0 and 1")
    return round(price * (1 - rate), 2)
