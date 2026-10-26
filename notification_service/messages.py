import html
from collections.abc import Sequence, Callable
from datetime import date
from decimal import Decimal
from enum import Enum

from membership_service.models import Membership
from payment_service.models import Payment
from plan_service.models import MembershipPlan
from user_service.models import User

_DASH = "-"
_MAX_VALUE_LENGTH = 200

_STATUS_LABELS = {
    Membership.Status.ACTIVE: "🟢 Active",
    Membership.Status.EXPIRED: "🔴 Expired",
    Membership.Status.FROZEN: "❄️ Frozen",
}

_TIER_LABELS = {
    MembershipPlan.Tier.BASIC: "🥉 Basic",
    MembershipPlan.Tier.STANDARD: "🥈 Standard",
    MembershipPlan.Tier.PREMIUM: "🥇 Premium",
}

_PAYMENT_TYPE_LABELS = {
    Payment.Type.MEMBERSHIP_PURCHASE: "🛒 Membership purchase",
    Payment.Type.UPGRADE_FEE: "⬆️ Upgrade fee",
}

_AUTO_RENEW_LABELS = {
    True: "🔄 Yes",
    False: "❌ No",
}


class NotificationEvent(str, Enum):
    """Events that produce a staff notification. Used by build_message()."""

    MEMBERSHIP_CREATED = "membership_created"
    MEMBERSHIP_ACTIVATED = "membership_activated"
    MEMBERSHIP_FROZEN = "membership_frozen"
    MEMBERSHIP_UNFROZEN = "membership_unfrozen"
    MEMBERSHIP_EXPIRED = "membership_expired"
    EXPIRATION_REMINDER = "expiration_reminder"
    PAYMENT_SUCCESS = "payment_success"


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


def _format_plan(plan: MembershipPlan) -> str:
    """Return the plan as "Name (code)". The only place with this format."""
    return f"{plan.name} ({plan.code})"


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


def _format_date(value: date | None) -> str:
    """Return a date formatted for a notification.

    Args:
        value (date | None): Date to format.

    Returns:
        str: The date as YYYY-MM-DD, or a dash when the date is None.
    """
    if value is None:
        return _DASH
    return value.isoformat()


def _format_days(count: int) -> str:
    """Return a number of days with the correct singular or plural form.

    Args:
        count (int): Number of days.

    Returns:
        str: "1 day" for one, otherwise e.g. "3 days".
    """
    return f"{count} day" if count == 1 else f"{count} days"


def _format_period(start: date | None, end: date | None, days: int | None = None) -> str:
    """Return a date range like "2026-01-01 → 2026-01-31 (30 days)".

    Args:
        start (date | None): First date of the range.
        end (date | None): Last date of the range.
        days (int | None): Number of days to show. When None, it is
            calculated as (end - start).days, so it always matches the dates.

    Returns:
        str: The formatted range, or a dash when a date is missing.
    """
    if start is None or end is None:
        return _DASH
    if days is None:
        days = (end - start).days
    return f"{_format_date(start)} → {_format_date(end)} ({_format_days(days)})"


def _prepare_value(value: object) -> str:
    """Return a value ready to be inserted into the HTML card.

    None becomes a dash, long text is cut to _MAX_VALUE_LENGTH characters
    (before escaping, so an HTML entity is never cut in half), then the text
    is escaped.
    """
    if value is None:
        return _DASH
    text = str(value)
    if len(text) > _MAX_VALUE_LENGTH:
        text = text[: _MAX_VALUE_LENGTH - 1] + "…"
    return html.escape(text, quote=False)


def _build_card(title: str, rows: Sequence[tuple[str, object]]) -> str:
    """Assemble an HTML notification from a title and label/value rows.

    This is the only place where HTML escaping happens. The title and all
    values are escaped, so callers must pass raw (unescaped) text. Labels are
    written by developers and are inserted as is. Values are converted to
    str before escaping, so None is shown as a dash and values longer than
    _MAX_VALUE_LENGTH are shortened with "…".

    Args:
        title (str): Event headline shown in bold at the top.
        rows (Sequence[tuple[str, object]]): Pairs of (label, value), shown
            one per line as "Label: value" with a bold label.

    Returns:
        str: HTML-formatted message (parse_mode=HTML).
    """
    lines = [f"<b>{label}:</b> {_prepare_value(value)}" for label, value in rows]
    return f"<b>{html.escape(title, quote=False)}</b>\n\n" + "\n".join(lines)


def build_membership_created_message(membership: Membership) -> str:
    """Build the notification text about a newly created membership.

    The text includes the member, plan name and code, tier, price paid,
    membership period, status, auto-renew flag and the membership id.

    Args:
        membership (Membership): The newly created membership. Its member
            and plan are read, so callers formatting many memberships
            should use select_related("member", "plan").

    Returns:
        str: HTML-formatted message ready to be sent to Telegram.
    """
    plan = membership.plan

    return _build_card(
        "🆕 New membership",
        [
            ("ID", f"#{membership.pk}"),
            ("Member", _format_member(membership.member)),
            ("Plan", f"{plan.name} ({plan.code})"),
            ("Tier", _TIER_LABELS.get(plan.tier, plan.tier)),
            ("Price paid", _format_money(membership.price_at_purchase)),
            ("Period", _format_period(membership.start_date, membership.end_date)),
            ("Status", _STATUS_LABELS.get(membership.status, membership.status)),
            ("Auto-renew", _AUTO_RENEW_LABELS[bool(membership.auto_renew)]),
        ],
    )


def build_membership_frozen_message(membership: Membership) -> str:
    """Build the notification text about a frozen membership.

    The text includes the member, plan, frozen period, the new end date
    (already shifted by the frozen days) and the membership id. Missing
    frozen dates are shown as a dash.

    Args:
        membership (Membership): The membership that was just frozen. Its
            member and plan are read, so callers formatting many memberships
            should use select_related("member", "plan").

    Returns:
        str: HTML-formatted message ready to be sent to Telegram.
    """
    if membership.frozen_from is None or membership.frozen_to is None:
        frozen_period = _DASH
    else:
        frozen_period = _format_period(
            membership.frozen_from,
            membership.frozen_to,
            days=membership.frozen_days,
        )

    return _build_card(
        "❄️ Membership frozen",
        [
            ("ID", f"#{membership.pk}"),
            ("Member", _format_member(membership.member)),
            ("Plan", _format_plan(membership.plan)),
            ("Frozen period", frozen_period),
            ("New end date", _format_date(membership.end_date)),
        ],
    )


def build_membership_activated_message(membership: Membership) -> str:
    """Build the notification text about a membership that became active.

    Sent when a membership leaves the initial FROZEN state after the first
    payment. The text includes the membership id, member, plan, the active
    period and the auto-renew flag.

    Args:
        membership (Membership): The membership that was just activated. Its
            member and plan are read, so callers formatting many memberships
            should use select_related("member", "plan").

    Returns:
        str: HTML-formatted message ready to be sent to Telegram.
    """
    return _build_card(
        "✅ Membership activated",
        [
            ("ID", f"#{membership.pk}"),
            ("Member", _format_member(membership.member)),
            ("Plan", _format_plan(membership.plan)),
            ("Status", _STATUS_LABELS.get(membership.status, membership.status)),
            ("Period", _format_period(membership.start_date, membership.end_date)),
            ("Auto-renew", _AUTO_RENEW_LABELS[bool(membership.auto_renew)]),
        ],
    )


def build_membership_unfrozen_message(membership: Membership) -> str:
    """Build the notification text about a membership that was unfrozen.

    The text includes the membership id, member, plan, the freeze period
    that has just ended, the current status and the end date.

    Args:
        membership (Membership): The membership that was just unfrozen. Its
            member and plan are read, so callers formatting many memberships
            should use select_related("member", "plan").

    Returns:
        str: HTML-formatted message ready to be sent to Telegram.
    """
    if membership.frozen_from is None or membership.frozen_to is None:
        frozen_period = _DASH
    else:
        frozen_period = _format_period(
            membership.frozen_from,
            membership.frozen_to,
            days=membership.frozen_days,
        )

    return _build_card(
        "🔥 Membership unfrozen",
        [
            ("ID", f"#{membership.pk}"),
            ("Member", _format_member(membership.member)),
            ("Plan", _format_plan(membership.plan)),
            ("Status", _STATUS_LABELS.get(membership.status, membership.status)),
            ("Was frozen", frozen_period),
            ("Ends", _format_date(membership.end_date)),
        ],
    )


def build_payment_success_message(payment: Payment) -> str:
    """Build the notification text about a successful payment.

    The text includes the member, payment type, amount, plan, membership id
    and payment id. The Stripe session url and id are intentionally left out.

    Args:
        payment (Payment): The payment that was just marked as paid. Its
            membership, member and plan are read, so callers should use
            select_related("membership__member", "membership__plan").

    Returns:
        str: HTML-formatted message ready to be sent to Telegram.
    """
    membership = payment.membership

    return _build_card(
        "💰 Payment received",
        [
            ("Payment ID", f"#{payment.pk}"),
            ("Member", _format_member(membership.member)),
            (
                "Type",
                _PAYMENT_TYPE_LABELS.get(payment.payment_type, payment.payment_type),
            ),
            ("Amount", _format_money(payment.money_to_pay)),
            ("Plan", _format_plan(membership.plan)),
            ("Membership ID", f"#{membership.pk}"),
        ],
    )


def build_membership_expired_message(membership: Membership) -> str:
    """Build the notification text about an expired membership.

    The text includes the membership id, member, plan, the date the
    membership ended and whether auto-renew is enabled.

    Args:
        membership (Membership): The membership that was marked as expired.
            Its member and plan are read, so callers formatting many
            memberships should use select_related("member", "plan").

    Returns:
        str: HTML-formatted message ready to be sent to Telegram.
    """
    return _build_card(
        "⌛ Membership expired",
        [
            ("ID", f"#{membership.pk}"),
            ("Member", _format_member(membership.member)),
            ("Plan", _format_plan(membership.plan)),
            ("Ended", _format_date(membership.end_date)),
            ("Auto-renew", _AUTO_RENEW_LABELS[bool(membership.auto_renew)]),
        ],
    )


def build_expiration_reminder_message(membership: Membership, days_left: int) -> str:
    """Build the reminder text about an upcoming membership expiration.

    The text includes the membership id, member, plan, end date and the
    number of days left, with correct singular and plural form ("1 day",
    "3 days").

    Args:
        membership (Membership): The membership that is about to expire. Its
            member and plan are read, so callers formatting many memberships
            should use select_related("member", "plan").
        days_left (int): Number of days until the end date (e.g. 7, 3 or 1).

    Returns:
        str: HTML-formatted message ready to be sent to Telegram.
    """
    return _build_card(
        "⏰ Membership expires soon",
        [
            ("ID", f"#{membership.pk}"),
            ("Member", _format_member(membership.member)),
            ("Plan", _format_plan(membership.plan)),
            ("Ends", _format_date(membership.end_date)),
            ("Days left", _format_days(days_left)),
        ],
    )


_BUILDERS: dict[NotificationEvent, Callable[..., str]] = {
    NotificationEvent.MEMBERSHIP_CREATED: build_membership_created_message,
    NotificationEvent.MEMBERSHIP_ACTIVATED: build_membership_activated_message,
    NotificationEvent.MEMBERSHIP_FROZEN: build_membership_frozen_message,
    NotificationEvent.MEMBERSHIP_UNFROZEN: build_membership_unfrozen_message,
    NotificationEvent.MEMBERSHIP_EXPIRED: build_membership_expired_message,
    NotificationEvent.EXPIRATION_REMINDER: build_expiration_reminder_message,
    NotificationEvent.PAYMENT_SUCCESS: build_payment_success_message,
}


def build_message(event: NotificationEvent | str, instance: Membership | Payment, **context) -> str:
    """Build the notification text for an event. Single entry point.

    Example:
        build_message(NotificationEvent.MEMBERSHIP_CREATED, membership)
        build_message(NotificationEvent.EXPIRATION_REMINDER, membership, days_left=3)

    Args:
        event (NotificationEvent | str): Event type, or its string value.
        instance (Membership | Payment): The object the event is about
            (a Payment for PAYMENT_SUCCESS, a Membership for the rest).
        **context: Extra arguments for the builder (days_left for
            EXPIRATION_REMINDER).

    Returns:
        str: HTML-formatted message ready to be sent to Telegram.

    Raises:
        ValueError: If the event is unknown.
    """
    try:
        builder = _BUILDERS[NotificationEvent(event)]
    except (KeyError, ValueError):
        raise ValueError(f"Unknown notification event: {event!r}") from None
    return builder(instance, **context)
