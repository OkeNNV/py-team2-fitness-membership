from rest_framework import serializers
from plan_service.models import MembershipPlan


class MembershipPlanSerializer(serializers.ModelSerializer):
    """Serializer for MembershipPlan model CRUD operations."""

    class Meta:
        """Meta configuration for MembershipPlanSerializer."""

        model = MembershipPlan
        fields = [
            "id",
            "name",
            "code",
            "duration_days",
            "price",
            "tier",
        ]
