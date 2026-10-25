from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from plan_service.models import MembershipPlan
from membership_service.models import Membership

User = get_user_model()


class MembershipModelTests(TestCase):
    """Test suite for Membership model custom properties and constraints."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123"
        )
        self.plan = MembershipPlan.objects.create(
            name="Base Plan",
            price=10.00,
            duration_days=30
        )

    def test_was_frozen_property(self):
        """Test was_frozen returns True if frozen_from is set, else False."""
        membership = Membership.objects.create(
            member=self.user,
            plan=self.plan,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            status=Membership.Status.ACTIVE,
            price_at_purchase=10.00
        )
        self.assertFalse(membership.was_frozen)

        membership.frozen_from = date.today()
        membership.frozen_to = date.today() + timedelta(days=5)
        self.assertTrue(membership.was_frozen)

    def test_frozen_days_property(self):
        """Test frozen_days correctly calculates duration of freeze."""
        start = date(2026, 10, 1)
        end = date(2026, 10, 6)
        membership = Membership.objects.create(
            member=self.user,
            plan=self.plan,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 10, 1),
            status=Membership.Status.FROZEN,
            price_at_purchase=10.00,
            frozen_from=start,
            frozen_to=end
        )

        self.assertEqual(membership.frozen_days, 5)

    def test_unique_active_or_frozen_constraint(self):
        """Test database constraint prevents multiple active/frozen memberships for one user."""
        Membership.objects.create(
            member=self.user,
            plan=self.plan,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            status=Membership.Status.ACTIVE,
            price_at_purchase=10.00
        )

        with self.assertRaises(IntegrityError):
            Membership.objects.create(
                member=self.user,
                plan=self.plan,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=30),
                status=Membership.Status.FROZEN,
                price_at_purchase=10.00
            )
