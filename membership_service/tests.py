from datetime import date
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from membership_service.models import Membership
from plan_service.models import MembershipPlan

User = get_user_model()


@pytest.mark.django_db
def test_membership_creation():
    """Test that a Membership instance can be created and properties work."""
    user = User.objects.create_user(email="test@example.com", password="password123")

    plan = MembershipPlan.objects.create(
        name="Base Plan",
        price=Decimal("10.00"),
        duration_days=30
    )

    membership = Membership.objects.create(
        member=user,
        plan=plan,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 2, 1),
        status=Membership.Status.ACTIVE,
        price_at_purchase=Decimal("10.00"),
    )

    assert membership.id is not None
    assert membership.was_frozen is False
    assert membership.frozen_days == 0
