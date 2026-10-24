"""Celery tasks for membership service."""

import logging

from celery import shared_task
from django.utils import timezone

from membership_service.models import Membership

logger = logging.getLogger(__name__)


@shared_task(ignore_result=True)
def mark_expired_memberships() -> int:
    """Mark ACTIVE memberships whose end_date is before today as EXPIRED.

    Runs once a day via Celery Beat. The update is a single SQL query and
    is idempotent: a repeated run finds nothing left to update.

    Returns:
        int: Number of memberships that were marked as expired.
    """
    today = timezone.localdate()

    updated = Membership.objects.filter(
        status=Membership.Status.ACTIVE,
        end_date__lt=today,
    ).update(status=Membership.Status.EXPIRED)

    logger.info("Marked %s membership(s) as EXPIRED (today=%s)", updated, today)
    return updated
