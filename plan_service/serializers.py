from drf_spectacular.utils import extend_schema_serializer, OpenApiExample
from rest_framework import serializers
from plan_service.models import MembershipPlan


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Valid Membership Plan Example",
            summary="Valid Membership Plan Example",
            description=(
                    "An example of a basic monthly subscription plan with valid price and duration."
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
