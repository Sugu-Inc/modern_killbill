"""Currency validation and formatting utilities for multi-currency billing."""

# ISO 4217 currency codes supported by the billing system
# Covers major currencies and common international markets
supported_currencies = [
    "USD",  # United States Dollar
    "EUR",  # Euro
    "GBP",  # British Pound Sterling
    "CAD",  # Canadian Dollar
    "AUD",  # Australian Dollar
    "NZD",  # New Zealand Dollar
    "JPY",  # Japanese Yen
    "CNY",  # Chinese Yuan
    "INR",  # Indian Rupee
    "BRL",  # Brazilian Real
    "MXN",  # Mexican Peso
    "CHF",  # Swiss Franc
    "SEK",  # Swedish Krona
    "NOK",  # Norwegian Krone
    "DKK",  # Danish Krone
    "SGD",  # Singapore Dollar
    "HKD",  # Hong Kong Dollar
    "KRW",  # South Korean Won
    "ZAR",  # South African Rand
    "PLN",  # Polish Złoty
    "THB",  # Thai Baht
    "MYR",  # Malaysian Ringgit
    "IDR",  # Indonesian Rupiah
    "PHP",  # Philippine Peso
    "TRY",  # Turkish Lira
]

# Currencies that don't use decimal places (smallest unit is whole currency)
# These currencies typically have no cents/pence/sen
zero_decimal_currencies = [
    "JPY",  # Japanese Yen
    "KRW",  # South Korean Won
    "VND",  # Vietnamese Đồng
    "CLP",  # Chilean Peso
    "ISK",  # Icelandic Króna
    "TWD",  # Taiwan Dollar
]

# Currency symbols for common currencies
currency_symbols = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "INR": "₹",
    "CAD": "CA$",
    "AUD": "A$",
    "NZD": "NZ$",
    "CHF": "CHF",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
    "BRL": "R$",
    "MXN": "MX$",
    "SGD": "S$",
    "HKD": "HK$",
    "KRW": "₩",
    "ZAR": "R",
    "PLN": "zł",
    "THB": "฿",
    "MYR": "RM",
    "IDR": "Rp",
    "PHP": "₱",
    "TRY": "₺",
}


def validate_currency(currency: str) -> bool:
    """
    Validate if a currency code is supported.

    Args:
        currency: ISO 4217 currency code (e.g., "USD", "EUR")

    Returns:
        True if currency is supported, False otherwise

    Example:
        >>> validate_currency("USD")
        True
        >>> validate_currency("XYZ")
        False
    """
    if not currency:
        return False

    return currency.upper() in supported_currencies


def format_amount_for_currency(amount: int, currency: str) -> str:
    """
    Format an amount in cents/smallest unit to a human-readable string.

    For zero-decimal currencies (JPY, KRW), the amount is already in whole units.
    For decimal currencies, the amount is in cents (e.g., 5000 cents = $50.00).

    Args:
        amount: Amount in smallest currency unit (cents for USD/EUR, whole yen for JPY)
        currency: ISO 4217 currency code

    Returns:
        Formatted string with currency symbol and amount

    Examples:
        >>> format_amount_for_currency(5000, "USD")
        '$50.00 USD'
        >>> format_amount_for_currency(5000, "EUR")
        '€50.00 EUR'
        >>> format_amount_for_currency(1000, "JPY")
        '¥1,000 JPY'
    """
    currency_upper = currency.upper()

    # Get currency symbol
    symbol = currency_symbols.get(currency_upper, currency_upper)

    # Check if zero-decimal currency
    if currency_upper in zero_decimal_currencies:
        # No decimal places - format as whole number with thousand separators
        formatted_amount = f"{amount:,}"
        return f"{symbol}{formatted_amount} {currency_upper}"
    else:
        # Decimal currency - convert cents to dollars/euros
        decimal_amount = amount / 100.0
        formatted_amount = f"{decimal_amount:,.2f}"
        return f"{symbol}{formatted_amount} {currency_upper}"


def get_currency_decimal_places(currency: str) -> int:
    """
    Get the number of decimal places for a currency.

    Args:
        currency: ISO 4217 currency code

    Returns:
        Number of decimal places (0 for JPY/KRW, 2 for USD/EUR)

    Example:
        >>> get_currency_decimal_places("USD")
        2
        >>> get_currency_decimal_places("JPY")
        0
    """
    if currency.upper() in zero_decimal_currencies:
        return 0
    return 2


def convert_to_smallest_unit(amount: float, currency: str) -> int:
    """
    Convert a decimal amount to smallest currency unit (cents).

    For zero-decimal currencies, returns the amount as-is.
    For decimal currencies, multiplies by 100.

    Args:
        amount: Amount in major currency units (e.g., 50.00 dollars)
        currency: ISO 4217 currency code

    Returns:
        Amount in smallest unit (cents for USD, whole yen for JPY)

    Examples:
        >>> convert_to_smallest_unit(50.00, "USD")
        5000
        >>> convert_to_smallest_unit(1000.0, "JPY")
        1000
    """
    if currency.upper() in zero_decimal_currencies:
        return int(amount)
    return int(amount * 100)


def convert_from_smallest_unit(amount: int, currency: str) -> float:
    """
    Convert from smallest currency unit (cents) to decimal amount.

    For zero-decimal currencies, returns the amount as-is.
    For decimal currencies, divides by 100.

    Args:
        amount: Amount in smallest unit (cents for USD, whole yen for JPY)
        currency: ISO 4217 currency code

    Returns:
        Amount in major currency units (dollars, euros, etc.)

    Examples:
        >>> convert_from_smallest_unit(5000, "USD")
        50.0
        >>> convert_from_smallest_unit(1000, "JPY")
        1000.0
    """
    if currency.upper() in zero_decimal_currencies:
        return float(amount)
    return amount / 100.0


def get_currency_symbol(currency: str) -> str:
    """
    Get the symbol for a currency code.

    Args:
        currency: ISO 4217 currency code

    Returns:
        Currency symbol (e.g., "$" for USD, "€" for EUR)

    Example:
        >>> get_currency_symbol("USD")
        '$'
        >>> get_currency_symbol("EUR")
        '€'
    """
    return currency_symbols.get(currency.upper(), currency.upper())


def currencies_match(currency1: str, currency2: str) -> bool:
    """
    Check if two currency codes match (case-insensitive).

    Args:
        currency1: First currency code
        currency2: Second currency code

    Returns:
        True if currencies match, False otherwise

    Example:
        >>> currencies_match("USD", "usd")
        True
        >>> currencies_match("EUR", "GBP")
        False
    """
    if not currency1 or not currency2:
        return False

    return currency1.upper() == currency2.upper()


def validate_currency_amount(amount: int, currency: str) -> bool:
    """
    Validate that an amount is valid for the given currency.

    Args:
        amount: Amount in smallest currency unit
        currency: ISO 4217 currency code

    Returns:
        True if amount is valid, False otherwise

    Example:
        >>> validate_currency_amount(5000, "USD")
        True
        >>> validate_currency_amount(-100, "EUR")
        False
    """
    # Amount must be non-negative
    if amount < 0:
        return False

    # Currency must be supported
    if not validate_currency(currency):
        return False

    return True
