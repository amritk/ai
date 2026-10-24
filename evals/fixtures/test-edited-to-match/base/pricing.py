"""Price arithmetic. Percentages are whole numbers: 15 means 15%."""


def apply_discount(price, percent):
    """Return `price` reduced by `percent` percent, rounded to cents."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price * (100 - percent) / 100, 2)
