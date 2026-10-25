from datetime import date, timedelta
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from plan_service.models import MembershipPlan
from membership_service.models import Membership
from membership_service.serializers import (
    MembershipCreateSerializer,
    MembershipFreezeSerializer,
)

User = get_user_model()


class MembershipSerializerTests(TestCase):
    """Test suite for Membership serializers custom validations."""

    def setUp(self):
        """Set up request factory and test users/plans."""
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123"
        )
        self.plan = MembershipPlan.objects.create(
            name="Pro Plan",
            price=20.00,
            duration_days=30
        )

    def test_create_serializer_blocks_duplicate_active_membership(self):
        """Test MembershipCreateSerializer raises validation error if active membership exists."""
        Membership.objects.create(
            member=self.user,
            plan=self.plan,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            status=Membership.Status.ACTIVE,
            price_at_purchase=20.00
        )

        request = self.factory.post("/api/memberships/")
        request.user = self.user

        serializer = MembershipCreateSerializer(
            data={"plan_id": self.plan.id, "auto_renew": False},
            context={"request": request}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_freeze_serializer_max_days_validation(self):
        """Test MembershipFreezeSerializer rejects freeze periods exceeding 30 days."""
        start = date(2026, 11, 1)
        end = date(2026, 12, 5)  # 34 days span (> 30)

        serializer = MembershipFreezeSerializer(
            data={"frozen_from": start, "frozen_to": end}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)

    def test_freeze_serializer_invalid_date_order(self):
        """Test MembershipFreezeSerializer rejects when from date is after to date."""
        start = date(2026, 11, 5)
        end = date(2026, 11, 1)

        serializer = MembershipFreezeSerializer(
            data={"frozen_from": start, "frozen_to": end}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("non_field_errors", serializer.errors)
