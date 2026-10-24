"""Celery tasks for notification service."""

import logging
import random

from celery import shared_task

from django.utils import timezone

logger = logging.getLogger(__name__)

from membership_service.models import Membership
from notification_service.exceptions import (
    PermanentTelegramError,
    TemporaryTelegramError,
)
from notification_service.messages import NotificationEvent, build_message
from notification_service.telegram_client import send_telegram_message_or_raise
from payment_service.models import Payment

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
RETRY_BASE_DELAY = 10  # seconds, doubles with every attempt
RETRY_MAX_DELAY = 300  # seconds, upper limit of the pause
RETRY_JITTER = 5  # seconds, random extra pause (0..RETRY_JITTER)

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


@shared_task(bind=True, ignore_result=True, max_retries=MAX_RETRIES)
def send_notification(self, event: str, object_id: int, context: dict | None = None) -> None:
    """Build a notification for an event and send it to the staff Telegram chat.

    Runs in a Celery worker. Only simple values are passed through the queue:
    the event name and the object id. The object is loaded from the database
    here, so the message is built from fresh data.

    Failures are handled like this:
        * unknown event or missing object: logged, the task ends, no retry;
        * permanent Telegram error (bad token, bot kicked, ...): the task
          ends, no retry (the Telegram client has already logged the reason);
        * temporary Telegram error (rate limit, network, 5xx): the task is
          retried up to MAX_RETRIES times. The pause is taken from Telegram
          (retry_after) when it is known, otherwise it grows exponentially
          with a little random jitter. After the last attempt the
          notification is dropped and an error is logged.

    Args:
        event (str): Value of NotificationEvent, e.g. "membership_created".
        object_id (int): Id of the object the event is about: a Payment for
            "payment_success", a Membership for all other events.
        context (dict | None): Extra arguments for the message builder, e.g.
            {"days_left": 3} for "expiration_reminder".
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
    except TemporaryTelegramError as exc:
        attempt = self.request.retries

        if attempt >= self.max_retries:
            logger.error(
                "Notification dropped after %s retries: %s id=%s",
                attempt,
                notification_event.value,
                object_id,
            )
            return

        if exc.retry_after is not None:
            delay = exc.retry_after + 1
        else:
            delay = min(RETRY_BASE_DELAY * 2**attempt, RETRY_MAX_DELAY)
            delay += random.uniform(0, RETRY_JITTER)

        logger.warning(
            "Notification will be retried: %s id=%s, attempt %s of %s, in %.0f s",
            notification_event.value,
            object_id,
            attempt + 1,
            self.max_retries,
            delay,
        )
        raise self.retry(exc=exc, countdown=delay)
