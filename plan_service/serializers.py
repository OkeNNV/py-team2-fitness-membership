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
