from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from rest_framework import serializers
from plan_service.models import MembershipPlan


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Valid Membership Plan Example",
            summary="Valid Membership Plan Example",
            description=(
                    "Available tiers for subscription: BASIC / STANDARD / PREMIUM"
            ),
            value={
                "name": "Monthly Basic",
                "code": "monthly-basic-01",
                "duration_days": 30,
                "price": "299.99",
                "tier": "BASIC"
            },
        ),
    ]
)
class MembershipPlanSerializer(serializers.ModelSerializer):
    """Serializer for MembershipPlan model CRUD operations."""

    class Meta:
        """Meta configuration for MembershipPlanSerializer."""

        model = MembershipPlan
        fields = [
            "id",
            "name",
            "code",
            "stripe_product_id",
            "duration_days",
            "price",
            "tier",
        ]
        read_only_fields = ["id", "stripe_product_id"]

    def validate_tier(self, value):
        """Validate that the tier is one of the allowed choices, formatting error with slashes."""
        valid_tiers = [choice[0] for choice in MembershipPlan.Tier.choices]
        if value not in valid_tiers:
            options_str = " / ".join(valid_tiers)
            raise serializers.ValidationError(
                f"Invalid tier. Available options: {options_str}"
            )
        return value
