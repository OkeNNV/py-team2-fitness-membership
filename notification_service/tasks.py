"""Celery tasks for notification service."""

import logging

from celery import shared_task

from membership_service.models import Membership
from notification_service.exceptions import PermanentTelegramError
from notification_service.messages import NotificationEvent, build_message
from notification_service.telegram_client import send_telegram_message_or_raise
from payment_service.models import Payment

logger = logging.getLogger(__name__)

# For every event: which model to load and which related objects to fetch
# in the same query (so build_message does not make extra queries).
_EVENT_SOURCES = {
    NotificationEvent.MEMBERSHIP_CREATED: (Membership, ("member", "plan")),
    NotificationEvent.MEMBERSHIP_FROZEN: (Membership, ("member", "plan")),
    NotificationEvent.MEMBERSHIP_EXPIRED: (Membership, ("member", "plan")),
    NotificationEvent.EXPIRATION_REMINDER: (Membership, ("member", "plan")),
    NotificationEvent.PAYMENT_SUCCESS: (
        Payment,
        ("membership__member", "membership__plan"),
    ),
}


@shared_task(bind=True, ignore_result=True)
def send_notification(self, event: str, object_id: int, context: dict | None = None) -> None:
    """Build a notification for an event and send it to the staff Telegram chat.

    Runs in a Celery worker. Only simple values are passed through the queue:
    the event name and the object id. The object is loaded from the database
    here, so the message is built from fresh data.

    Nothing is retried yet: an unknown event, a missing object or a permanent
    Telegram error end the task quietly, and a temporary Telegram error is
    raised so the task is marked as failed.

    Args:
        event (str): Value of NotificationEvent, e.g. "membership_created".
        object_id (int): Id of the object the event is about: a Payment for
            "payment_success", a Membership for all other events.
        context (dict | None): Extra arguments for the message builder, e.g.
            {"days_left": 3} for "expiration_reminder".

    Raises:
        TemporaryTelegramError: Telegram is temporarily unavailable.
    """
    try:
        notification_event = NotificationEvent(event)
    except ValueError:
        logger.error("Notification skipped: unknown event %r", event)
        return

    model, related = _EVENT_SOURCES[notification_event]

    try:
        obj = model.objects.select_related(*related).get(pk=object_id)
    except model.DoesNotExist:
        logger.warning(
            "Notification skipped: %s with id=%s does not exist",
            notification_event.value,
            object_id,
        )
        return

    message = build_message(notification_event, obj, **(context or {}))

    try:
        send_telegram_message_or_raise(message)
    except PermanentTelegramError:
        # Already logged by the Telegram client, retrying cannot help.
        return
