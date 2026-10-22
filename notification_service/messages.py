from decimal import Decimal

from user_service.models import User


def _format_member(user: User) -> str:
    """Return a human-readable description of a member for a notification.

    Args:
        user (User): Club member or staff user.

    Returns:
        str: "First Last (email)" when the name is known, "First (email)" or
            "Last (email)" when only one part is set, or just the email when
            both name fields are empty.
    """
    full_name = user.get_full_name()
    email = user.email

    if full_name:
        return f"{full_name} ({email})"
    return email


def _format_money(amount: Decimal) -> str:
    """Return a money amount formatted for a notification.

    The amount is shown with exactly two decimal places followed by the
    currency code, e.g. Decimal("9.5") becomes "9.50 USD".

    Args:
        amount (Decimal): Amount in USD.

    Returns:
        str: Formatted amount with the currency code.
    """
    return f"{amount:.2f} USD"
