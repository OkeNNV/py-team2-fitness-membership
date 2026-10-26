from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from payment_service.models import Payment
from plan_service.models import MembershipPlan
from membership_service.models import Membership

User = get_user_model()


class MembershipViewSetTests(APITestCase):
    """Test suite for MembershipViewSet custom actions (freeze, resume, upgrade)."""

    def setUp(self):
        """Set up users, plans, and authenticated client."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="password123"
        )
        self.plan_basic = MembershipPlan.objects.create(
            name="Basic",
            code="BASIC_PLAN",
            price=10.00,
            duration_days=30
        )
        self.plan_pro = MembershipPlan.objects.create(
            name="Pro",
            code="PRO_PLAN",
            price=30.00,
            duration_days=30
        )

        self.client.force_authenticate(user=self.user)

        self.membership = Membership.objects.create(
            member=self.user,
            plan=self.plan_basic,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            status=Membership.Status.ACTIVE,
            price_at_purchase=10.00
        )

    def test_freeze_active_membership(self):
        """Test successfully freezing an active membership using query parameter 'to'."""
        url = reverse("membership-detail", kwargs={"pk": self.membership.id}) + "freeze/"
        freeze_to_date = (date.today() + timedelta(days=5)).isoformat()

        response = self.client.post(f"{url}?to={freeze_to_date}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, Membership.Status.FROZEN)
        self.assertTrue(self.membership.was_frozen)

    def test_freeze_already_frozen_membership_fails(self):
        """Test that freezing a membership twice is rejected."""
        self.membership.status = Membership.Status.FROZEN
        self.membership.frozen_from = date.today()
        self.membership.frozen_to = date.today() + timedelta(days=5)
        self.membership.save()

        url = reverse("membership-detail", kwargs={"pk": self.membership.id}) + "freeze/"
        freeze_to_date = (date.today() + timedelta(days=5)).isoformat()

        response = self.client.post(f"{url}?to={freeze_to_date}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resume_frozen_membership(self):
        """Test successfully resuming a frozen membership back to ACTIVE."""
        self.membership.status = Membership.Status.FROZEN
        self.membership.frozen_from = date.today()
        self.membership.frozen_to = date.today() + timedelta(days=5)
        self.membership.save()

        Payment.objects.create(
            membership=self.membership,
            payment_type=Payment.Type.MEMBERSHIP_PURCHASE,
            status=Payment.Status.PAID,
            money_to_pay=Decimal("10.00"),
        )

        url = reverse("membership-detail", kwargs={"pk": self.membership.id}) + "resume/"
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, Membership.Status.ACTIVE)
        self.assertIsNone(self.membership.frozen_from)
