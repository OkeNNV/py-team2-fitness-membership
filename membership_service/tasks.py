"""Celery tasks for membership service."""

from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from membership_service.models import Membership
from notification_service.services import notify_membership_expired, notify_expiration_reminder

REMINDER_DAYS = (7, 3, 1)


@shared_task(ignore_result=True)
def mark_expired_memberships() -> int:
    """Mark ACTIVE memberships whose end_date is before today as EXPIRED.

    Runs once a day via Celery Beat. After the update is committed, staff
    get one Telegram notification per membership that was marked.

    Returns:
        int: Number of memberships that were marked as expired.
    """
    today = timezone.localdate()

    with transaction.atomic():
        memberships = list(
            Membership.objects.select_for_update()
            .filter(status=Membership.Status.ACTIVE, end_date__lt=today)
        )
        ids = [membership.pk for membership in memberships]

        if not ids:
            return 0

        Membership.objects.filter(pk__in=ids).update(
            status=Membership.Status.EXPIRED
        )

        for membership in memberships:
            notify_membership_expired(membership)

    return len(ids)


@shared_task(ignore_result=True)
def send_expiration_reminders() -> int:
    """Remind staff about ACTIVE memberships ending in 7, 3 or 1 day(s).

    Runs once a day via Celery Beat. A membership is matched when its
    end_date is exactly today + N days, so each membership gets at most
    one reminder per threshold.

    Returns:
        int: Number of reminders queued.
    """
    today = timezone.localdate()
    sent = 0

    for days_left in REMINDER_DAYS:
        target_date = today + timedelta(days=days_left)

        memberships = Membership.objects.filter(
            status=Membership.Status.ACTIVE,
            end_date=target_date,
        )

        for membership in memberships:
            notify_expiration_reminder(membership, days_left)
            sent += 1

    return sent


@shared_task(ignore_result=True)
def unfreeze_memberships() -> int:
    """Activate memberships whose freeze period has ended."""
    today = timezone.localdate()

    return Membership.objects.filter(
        status=Membership.Status.FROZEN,
        frozen_to__lte=today,
    ).update(status=Membership.Status.ACTIVE)
