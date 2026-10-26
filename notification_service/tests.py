import asyncio
import logging
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import SendMessage
from celery.exceptions import Retry
from django.contrib.auth import get_user_model

from membership_service.models import Membership
from notification_service import messages
from notification_service.exceptions import PermanentTelegramError, TemporaryTelegramError
from notification_service.messages import NotificationEvent, build_message
from notification_service.services import (
    notify_expiration_reminder,
    notify_membership_activated,
    notify_membership_created,
    notify_membership_unfrozen,
    notify_payment_success,
)
from notification_service.tasks import MAX_RETRIES, send_notification
from notification_service.telegram_client import (
    MESSAGE_MAX_LENGTH,
    send_telegram_message,
    send_telegram_message_or_raise,
)
from payment_service.models import Payment
from plan_service.models import MembershipPlan

User = get_user_model()

TOKEN = "123456:ABCdefGhIJKlmNoPQRsTUVwxyZ"
METHOD = SendMessage(chat_id=1, text="x")  # needed to build aiogram errors


# --------------------------------------------------------------------------- #
# Telegram client
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def telegram_settings(settings):
    """Give every test a fake bot token and chat id."""
    settings.TELEGRAM_BOT_TOKEN = TOKEN
    settings.TELEGRAM_CHAT_ID = "-100123"
    settings.TELEGRAM_TIMEOUT = 10


@pytest.fixture
def send():
    """Replace aiogram's Bot.send_message with an async mock (no network)."""
    with patch("aiogram.Bot.send_message", new=AsyncMock()) as mock:
        yield mock


def test_message_is_sent_as_html(send):
    """A valid message is sent to the configured chat with HTML parse mode."""
    assert send_telegram_message("<b>hi</b>") is True

    send.assert_awaited_once()
    assert send.await_args.kwargs["text"] == "<b>hi</b>"
    assert send.await_args.kwargs["parse_mode"] == "HTML"
    assert send.await_args.kwargs["chat_id"] == "-100123"


@pytest.mark.parametrize(
    ("token", "chat_id", "text"),
    [("", "-100123", "hi"), (TOKEN, "", "hi"), (TOKEN, "-100123", "   ")],
    ids=["no token", "no chat id", "empty message"],
)
def test_nothing_is_sent_when_not_configured_or_empty(settings, send, token, chat_id, text):
    """Missing configuration or an empty text is a permanent error and sends nothing."""
    settings.TELEGRAM_BOT_TOKEN = token
    settings.TELEGRAM_CHAT_ID = chat_id

    assert send_telegram_message(text) is False
    with pytest.raises(PermanentTelegramError):
        send_telegram_message_or_raise(text)
    send.assert_not_awaited()


def test_long_message_is_truncated(send):
    """A message over the Telegram limit is cut and ends with three dots."""
    send_telegram_message("a" * (MESSAGE_MAX_LENGTH + 500))

    text = send.await_args.kwargs["text"]
    assert len(text) == MESSAGE_MAX_LENGTH
    assert text.endswith("...")


def test_rate_limit_is_temporary_and_keeps_retry_after(send):
    """Telegram 429 becomes a temporary error that carries the requested pause."""
    send.side_effect = TelegramRetryAfter(METHOD, "Too Many Requests", 5)

    with pytest.raises(TemporaryTelegramError) as exc_info:
        send_telegram_message_or_raise("hi")

    assert exc_info.value.retry_after == 5


@pytest.mark.parametrize(
    "error",
    [TelegramNetworkError(METHOD, "timeout"), TelegramServerError(METHOD, "Bad Gateway")],
    ids=["network", "server"],
)
def test_network_and_server_errors_are_temporary(send, error):
    """Network problems and Telegram 5xx may go away, so they are temporary."""
    send.side_effect = error

    with pytest.raises(TemporaryTelegramError):
        send_telegram_message_or_raise("hi")


@pytest.mark.parametrize(
    "error",
    [
        TelegramBadRequest(METHOD, "Bad Request: chat not found"),
        TelegramForbiddenError(METHOD, "Forbidden: bot was kicked"),
        TelegramMigrateToChat(METHOD, "group chat was upgraded", -1009),
    ],
    ids=["bad request", "forbidden", "chat migrated"],
)
def test_client_errors_are_permanent_and_not_resent(send, error):
    """Errors that a retry cannot fix are permanent, and the text is sent only once."""
    send.side_effect = error

    with pytest.raises(PermanentTelegramError):
        send_telegram_message_or_raise("hi")
    assert send.await_count == 1


def test_rejected_markup_is_resent_as_plain_text(send):
    """If Telegram cannot parse the HTML, the text is resent once without tags."""
    send.side_effect = [TelegramBadRequest(METHOD, "Bad Request: can't parse entities"), None]

    assert send_telegram_message("<b>Ann &lt;Lee&gt;</b> <i") is True

    assert send.await_count == 2
    assert send.await_args.kwargs["parse_mode"] is None
    assert send.await_args.kwargs["text"] == "Ann <Lee> "


def test_called_from_running_event_loop_returns_false(send):
    """The sender must not be used from async code, it refuses and sends nothing."""

    async def call():
        return send_telegram_message("hi")

    assert asyncio.run(call()) is False
    send.assert_not_awaited()


def test_token_is_never_logged_or_raised(send, caplog):
    """The bot token does not appear in logs, exception text or exception chain."""
    caplog.set_level(logging.DEBUG)
    send.side_effect = TelegramNetworkError(METHOD, f"cannot reach .../bot{TOKEN}/sendMessage")

    with pytest.raises(TemporaryTelegramError) as exc_info:
        send_telegram_message_or_raise("hi")

    assert TOKEN not in caplog.text
    assert TOKEN not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


# --------------------------------------------------------------------------- #
# Message builders (no database needed)
# --------------------------------------------------------------------------- #


def make_membership(**overrides):
    """Build a lightweight membership-like object for message tests."""
    user = SimpleNamespace(email="ann@example.com", get_full_name=lambda: "Ann <Lee>")
    plan = SimpleNamespace(
        name="Gold & Co",
        code="gold",
        tier=MembershipPlan.Tier.PREMIUM,
        duration_days=30,
    )
    data = {
        "pk": 7,
        "member": user,
        "plan": plan,
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
        "status": Membership.Status.ACTIVE,
        "auto_renew": True,
        "price_at_purchase": Decimal("9.5"),
        "frozen_from": None,
        "frozen_to": None,
        "frozen_days": 0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_created_message_has_details_and_escapes_html():
    """The card contains the main facts and user text is HTML-escaped."""
    text = messages.build_membership_created_message(make_membership())

    assert "<b>🆕 New membership</b>" in text
    assert "Ann &lt;Lee&gt; (ann@example.com)" in text
    assert "Gold &amp; Co (gold)" in text
    assert "9.50 USD" in text
    assert "2026-01-01 → 2026-01-31 (30 days)" in text


def test_created_message_handles_none_auto_renew_and_real_period():
    """auto_renew=None does not crash, and the period is counted from the dates."""
    membership = make_membership(auto_renew=None, end_date=date(2026, 2, 10))

    text = messages.build_membership_created_message(membership)

    assert "❌ No" in text
    assert "(40 days)" in text


def test_card_shows_dash_for_none_and_shortens_long_values():
    """None becomes a dash and a very long value is cut with an ellipsis."""
    text = messages._build_card("Title", [("Empty", None), ("Long", "a" * 500)])

    assert "<b>Empty:</b> -" in text
    assert "None" not in text
    assert "…" in text
    assert len(text) < 300


def test_frozen_message_without_and_with_dates():
    """The frozen period is a dash without dates and uses frozen_days with dates."""
    without = messages.build_membership_frozen_message(make_membership())
    with_dates = messages.build_membership_frozen_message(
        make_membership(
            frozen_from=date(2026, 1, 10),
            frozen_to=date(2026, 1, 20),
            frozen_days=10,
            end_date=date(2026, 2, 10),
        )
    )

    assert "<b>Frozen period:</b> -" in without
    assert "2026-01-10 → 2026-01-20 (10 days)" in with_dates


def test_reminder_uses_singular_and_plural_days():
    """'1 day' for one, '3 days' for more."""
    membership = make_membership()

    one = messages.build_expiration_reminder_message(membership, 1)
    three = messages.build_expiration_reminder_message(membership, 3)

    assert "<b>Days left:</b> 1 day" in one
    assert "1 days" not in one
    assert "<b>Days left:</b> 3 days" in three


def test_payment_message_has_no_stripe_data():
    """The payment card shows the amount and type but never the Stripe session."""
    payment = SimpleNamespace(
        pk=3,
        membership=make_membership(),
        payment_type=Payment.Type.UPGRADE_FEE,
        money_to_pay=Decimal("20"),
        session_url="https://stripe.example/session",
        session_id="cs_test_123",
    )

    text = messages.build_payment_success_message(payment)

    assert "20.00 USD" in text
    assert "⬆️ Upgrade fee" in text
    assert "stripe.example" not in text
    assert "cs_test_123" not in text


def test_activated_message_shows_active_status_and_period():
    """The activation card shows the new status, the plan and the active period."""
    text = messages.build_membership_activated_message(make_membership())

    assert "✅ Membership activated" in text
    assert "🟢 Active" in text
    assert "Gold &amp; Co (gold)" in text
    assert "2026-01-01 → 2026-01-31 (30 days)" in text


def test_unfrozen_message_shows_ended_freeze_and_end_date():
    """The unfreeze card shows the freeze that ended; no dates give a dash."""
    without = messages.build_membership_unfrozen_message(make_membership())
    with_dates = messages.build_membership_unfrozen_message(
        make_membership(
            frozen_from=date(2026, 1, 10),
            frozen_to=date(2026, 1, 20),
            frozen_days=10,
            end_date=date(2026, 2, 10),
        )
    )

    assert "🔥 Membership unfrozen" in with_dates
    assert "<b>Was frozen:</b> -" in without
    assert "2026-01-10 → 2026-01-20 (10 days)" in with_dates
    assert "<b>Ends:</b> 2026-02-10" in with_dates


def test_build_message_picks_builder_and_rejects_unknown_event():
    """build_message dispatches by event (enum or string) and fails on unknown ones."""
    membership = make_membership()

    assert build_message(NotificationEvent.MEMBERSHIP_CREATED, membership) == (
        messages.build_membership_created_message(membership)
    )
    assert "3 days" in build_message("expiration_reminder", membership, days_left=3)
    with pytest.raises(ValueError):
        build_message("no_such_event", membership)


# --------------------------------------------------------------------------- #
# Celery task
# --------------------------------------------------------------------------- #


@pytest.fixture
def membership(db):
    """Create a saved membership with its member and plan."""
    user = User.objects.create_user(
        email="ann@example.com", password="password123", first_name="Ann", last_name="Lee"
    )
    plan = MembershipPlan.objects.create(
        name="Gold", code="gold", price=Decimal("49.99"), duration_days=30
    )
    return Membership.objects.create(
        member=user,
        plan=plan,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        status=Membership.Status.ACTIVE,
        price_at_purchase=plan.price,
    )


@pytest.fixture
def telegram_send():
    """Replace the Telegram sender used by the task."""
    with patch("notification_service.tasks.send_telegram_message_or_raise") as mock:
        yield mock


@pytest.fixture
def task_retry():
    """Replace task.retry with a mock that raises Retry, like Celery does."""
    with patch.object(send_notification, "retry", Mock(side_effect=Retry())) as mock:
        yield mock


@contextmanager
def after_retries(count):
    """Run the task as if it had already been retried `count` times."""
    send_notification.push_request(retries=count)
    try:
        yield
    finally:
        send_notification.pop_request()


@pytest.mark.parametrize(
    ("event", "title"),
    [
        ("membership_activated", "Membership activated"),
        ("membership_unfrozen", "Membership unfrozen"),
        ("membership_expired", "Membership expired"),
    ],
)
def test_task_sends_status_change_events(membership, telegram_send, event, title):
    """Every status-change event is loaded from the database and sent."""
    send_notification.run(event, membership.pk)

    telegram_send.assert_called_once()
    assert title in telegram_send.call_args.args[0]


def test_task_builds_and_sends_the_message(membership, telegram_send):
    """The task loads the membership from the database and sends its card."""
    send_notification.run("membership_created", membership.pk)

    telegram_send.assert_called_once()
    assert "ann@example.com" in telegram_send.call_args.args[0]


@pytest.mark.parametrize(
    ("event", "object_id"),
    [("no_such_event", 1), ("membership_created", 999999)],
    ids=["unknown event", "missing object"],
)
def test_task_skips_unknown_event_and_missing_object(telegram_send, db, event, object_id):
    """Nothing is sent, and nothing fails, for an unknown event or a deleted object."""
    send_notification.run(event, object_id)

    telegram_send.assert_not_called()


def test_task_does_not_retry_permanent_errors(membership, telegram_send, task_retry):
    """A permanent Telegram error ends the task without a retry."""
    telegram_send.side_effect = PermanentTelegramError("bad token")

    send_notification.run("membership_created", membership.pk)

    task_retry.assert_not_called()


def test_task_waits_as_long_as_telegram_asks(membership, telegram_send, task_retry):
    """On a rate limit the task retries after retry_after plus one second."""
    telegram_send.side_effect = TemporaryTelegramError("rate limit", retry_after=7)

    with pytest.raises(Retry):
        send_notification.run("membership_created", membership.pk)

    assert task_retry.call_args.kwargs["countdown"] == 8


def test_task_backs_off_exponentially_without_retry_after(membership, telegram_send, task_retry):
    """Without retry_after the pause doubles with every attempt, plus a little jitter."""
    telegram_send.side_effect = TemporaryTelegramError("network")

    with after_retries(2), pytest.raises(Retry):
        send_notification.run("membership_created", membership.pk)

    assert 40 <= task_retry.call_args.kwargs["countdown"] <= 45


def test_task_gives_up_after_max_retries(membership, telegram_send, task_retry, caplog):
    """After the last attempt the notification is dropped and an error is logged."""
    telegram_send.side_effect = TemporaryTelegramError("network")

    with after_retries(MAX_RETRIES):
        send_notification.run("membership_created", membership.pk)

    task_retry.assert_not_called()
    assert "dropped" in caplog.text


# --------------------------------------------------------------------------- #
# Service functions used by other apps
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("notify", "arg", "event", "context"),
    [
        (notify_membership_created, SimpleNamespace(pk=5), "membership_created", None),
        (notify_payment_success, SimpleNamespace(pk=6), "payment_success", None),
        (notify_membership_activated, SimpleNamespace(pk=7), "membership_activated", None),
        (notify_membership_unfrozen, SimpleNamespace(pk=8), "membership_unfrozen", None),
    ],
    ids=["membership created", "payment success", "membership activated", "membership unfrozen"],
)
def test_notify_queues_task_only_after_commit(
    django_capture_on_commit_callbacks, notify, arg, event, context
):
    """The task is queued with simple values, and only when the transaction commits."""
    with patch("notification_service.services.send_notification") as task:
        with django_capture_on_commit_callbacks(execute=True):
            notify(arg)
            task.delay.assert_not_called()

        task.delay.assert_called_once_with(event=event, object_id=arg.pk, context=context)


@pytest.mark.django_db
def test_notify_never_raises_when_queue_is_down(django_capture_on_commit_callbacks, caplog):
    """If Redis is unavailable the caller is not affected and the error is logged."""
    with patch("notification_service.services.send_notification") as task:
        task.delay.side_effect = OSError("redis is down")

        with django_capture_on_commit_callbacks(execute=True):
            notify_expiration_reminder(SimpleNamespace(pk=5), 3)

    assert "Could not queue notification" in caplog.text
