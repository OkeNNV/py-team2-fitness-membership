from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from plan_service.models import MembershipPlan


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Valid Membership Plan Example",
            summary="Valid Membership Plan Example",
            description=(
                "Available tiers for subscription: "
                "BASIC / STANDARD / PREMIUM"
            ),
            value={
                "name": "Monthly Basic",
                "code": "monthly-basic-01",
                "duration_days": 30,
                "price": "299.99",
                "tier": "BASIC",
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

    def validate(self, attrs):
        """Prevent billing changes after a plan is synchronized with Stripe."""
        plan = self.instance

        if plan is None or not plan.stripe_product_id:
            return attrs

        errors = {}

        for field in ("price", "duration_days"):
            if field in attrs and attrs[field] != getattr(plan, field):
                errors[field] = (
                    "This field cannot be changed after the plan is "
                    "synchronized with Stripe. Create a new plan instead."
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def validate_tier(self, value):
        """Validate tier and format available choices with slashes."""
        valid_tiers = [choice[0] for choice in MembershipPlan.Tier.choices]
        if value not in valid_tiers:
            options_str = " / ".join(valid_tiers)
            raise serializers.ValidationError(
                f"Invalid tier. Available options: {options_str}"
            )
        return value
