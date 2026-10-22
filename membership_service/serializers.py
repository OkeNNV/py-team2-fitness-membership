from datetime import date
from rest_framework import serializers
from .models import Membership
# from plan_service.serializers import MembershipPlanSerializer
# from payment_service.serializers import PaymentSerializer


class MembershipSerializer(serializers.ModelSerializer):
    """Serializer for reading membership details."""
    # plan_detail = MembershipPlanSerializer(source="plan", read_only=True)
    # payments = PaymentSerializer(many=True, read_only=True)
    was_frozen = serializers.BooleanField(read_only=True)
    frozen_days = serializers.IntegerField(read_only=True)

    class Meta:
        model = Membership
        fields = [
            "id",
            "member",
            "plan",
            # "plan_detail",
            "start_date",
            "end_date",
            "status",
            "auto_renew",
            "price_at_purchase",
            "frozen_from",
            "frozen_to",
            "was_frozen",
            "frozen_days",
            # "payments",
        ]
        read_only_fields = [
            "id",
            "member",
            "start_date",
            "end_date",
            "status",
            "price_at_purchase",
            "frozen_from",
            "frozen_to",
        ]


class MembershipCreateSerializer(serializers.ModelSerializer):
    """Serializer used for purchasing a new membership plan."""
    plan_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Membership
        fields = ["plan_id", "auto_renew"]

    def validate(self, attrs):
        user = self.context["request"].user
        if Membership.objects.filter(member=user, status__in=["ACTIVE", "FROZEN"]).exists():
            raise serializers.ValidationError(
                "The user already has an active or frozen membership."
            )
        return attrs


class MembershipFreezeSerializer(serializers.Serializer):
    """Serializer for validating membership freeze date range."""
    frozen_from = serializers.DateField()
    frozen_to = serializers.DateField()

    def validate(self, attrs):
        frozen_from = attrs.get("frozen_from")
        frozen_to = attrs.get("frozen_to")

        if frozen_from > frozen_to:
            raise serializers.ValidationError("Freeze start date cannot be later than the end date.")

        freeze_days = (frozen_to - frozen_from).days + 1
        if freeze_days > 30:
            raise serializers.ValidationError("Maximum freeze window cannot exceed 30 days.")

        return attrs
