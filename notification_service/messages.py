from decimal import Decimal

from membership_service.models import Membership
from payment_service.models import Payment
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


def build_membership_created_message(membership: Membership) -> str:
    """Build the notification text about a newly created membership.

    The text includes the member, plan name and code, tier, price paid,
    membership period, status, auto-renew flag and the membership id.

    Args:
        membership (Membership): The newly created membership. Its member
            and plan are read, so callers formatting many memberships
            should use select_related("member", "plan").

    Returns:
        str: Plain-text message ready to be sent to Telegram.
    """
    member = _format_member(membership.member)
    plan_name = membership.plan.name
    plan_code = membership.plan.code
    plan_tier = membership.plan.tier
    plan_price = _format_money(membership.plan.price)
    membership_period = membership.end_date - membership.start_date
    membership_status = membership.status
    membership_auto_renew = membership.auto_renew
    membership_id = membership.pk


def build_membership_frozen_message(membership: Membership) -> str:
    """Build the notification text about a frozen membership.

    The text includes the member, plan, frozen period, the new end date
    (already shifted by the frozen days) and the membership id. Missing
    frozen dates are shown as a dash.

    Args:
        membership (Membership): The membership that was just frozen.

    Returns:
        str: Plain-text message ready to be sent to Telegram.
    """


def build_payment_success_message(payment: Payment) -> str:
    """Build the notification text about a successful payment.

    The text includes the member, payment type, amount, plan, membership id
    and payment id. The Stripe session url and id are intentionally left out.

    Args:
        payment (Payment): The payment that was just marked as paid. Its
            membership, member and plan are read.

    Returns:
        str: Plain-text message ready to be sent to Telegram.
    """


def build_membership_expired_message(membership: Membership) -> str:
    """Build the notification text about an expired membership.

    The text includes the member, plan, the date the membership ended
    and whether auto-renew is enabled.

    Args:
        membership (Membership): The membership that was marked as expired.

    Returns:
        str: Plain-text message ready to be sent to Telegram.
    """


def build_expiration_reminder_message(membership: Membership, days_left: int) -> str:
    """Build the reminder text about an upcoming membership expiration.

    The text includes the member, plan, end date and the number of days
    left, with correct singular and plural form ("1 day", "3 days").

    Args:
        membership (Membership): The membership that is about to expire.
        days_left (int): Number of days until the end date (e.g. 7, 3 or 1).

    Returns:
        str: Plain-text message ready to be sent to Telegram.
    """
