"""Public functions for sending staff notifications to Telegram.

This is the only way for other apps to send a notification. Call one of the
``notify_*`` functions and do not call the Celery task directly.

Every function puts a task into the queue after the current database
transaction is committed (so a rolled-back change never produces a
notification) and never raises: if the queue is not available, the error is
logged and the caller continues as usual.
"""

import logging

from django.db import transaction

from membership_service.models import Membership
from notification_service.messages import NotificationEvent
from notification_service.tasks import send_notification
from payment_service.models import Payment

logger = logging.getLogger(__name__)


def _enqueue(
    event: NotificationEvent,
    object_id: int,
    context: dict | None = None,
) -> None:
    """Queue a notification task once the current transaction is committed.

    Only simple values go through the queue: the event name, the object id
    and a small context dict. If there is no open transaction, the task is
    queued immediately.

    Args:
        event (NotificationEvent): The event to notify about.
        object_id (int): Id of the object the event is about.
        context (dict | None): Extra arguments for the message builder.
    """

    def push() -> None:
        try:
            send_notification.delay(
                event=event.value,
                object_id=object_id,
                context=context,
            )
        except Exception as exc:
            # Only the type is logged: the text may contain the broker url.
            logger.error(
                "Could not queue notification %s id=%s: %s",
                event.value,
                object_id,
                type(exc).__name__,
            )

    transaction.on_commit(push)


def notify_membership_created(membership: Membership) -> None:
    """Notify staff about a newly created membership.

    Args:
        membership (Membership): The membership that was just created.
    """
    _enqueue(NotificationEvent.MEMBERSHIP_CREATED, membership.pk)


def notify_membership_activated(membership: Membership) -> None:
    """Notify staff that a membership became active after the first payment.

    Call it after the status is saved as ACTIVE, and only when the status
    really changed, so a repeated webhook does not send a second message.

    Args:
        membership (Membership): The membership that was just activated.
    """
    _enqueue(NotificationEvent.MEMBERSHIP_ACTIVATED, membership.pk)


def notify_membership_unfrozen(membership: Membership) -> None:
    """Notify staff that a frozen membership was unfrozen (set back to ACTIVE).

    Call it after the status is saved as ACTIVE. It is used both for a manual
    resume and for the automatic unfreeze when the freeze period ends.

    Args:
        membership (Membership): The membership that was just unfrozen.
    """
    _enqueue(NotificationEvent.MEMBERSHIP_UNFROZEN, membership.pk)


def notify_membership_frozen(membership: Membership) -> None:
    """Notify staff that a membership was frozen.

    Call it after the freeze is saved, so the new end date is already set.

    Args:
        membership (Membership): The membership that was just frozen.
    """
    _enqueue(NotificationEvent.MEMBERSHIP_FROZEN, membership.pk)


def notify_membership_expired(membership: Membership) -> None:
    """Notify staff that a membership was marked as expired.

    Args:
        membership (Membership): The membership that was just marked as expired.
    """
    _enqueue(NotificationEvent.MEMBERSHIP_EXPIRED, membership.pk)


def notify_expiration_reminder(membership: Membership, days_left: int) -> None:
    """Remind staff that a membership is about to expire.

    Args:
        membership (Membership): The membership that is about to expire.
        days_left (int): Number of days until the end date (e.g. 7, 3 or 1).
    """
    _enqueue(
        NotificationEvent.EXPIRATION_REMINDER,
        membership.pk,
        context={"days_left": days_left},
    )


def notify_payment_success(payment: Payment) -> None:
    """Notify staff about a successful payment.

    Call it only when the payment really changes its status to PAID, so a
    repeated visit of the success page does not send a second notification.

    Args:
        payment (Payment): The payment that was just marked as paid.
    """
    _enqueue(NotificationEvent.PAYMENT_SUCCESS, payment.pk)
