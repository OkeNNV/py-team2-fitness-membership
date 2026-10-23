"""Celery tasks for notification service."""

from datetime import datetime

from celery import shared_task


#### Test task for development ####
@shared_task
def print_hello():
    """Print a message to the console (smoke test for Celery Beat)."""
    print(f"[Celery] Hello from periodic task at {datetime.now():%H:%M:%S}")
