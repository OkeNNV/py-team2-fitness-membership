from rest_framework import serializers

from payment_service.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = (
            "id",
            "status",
            "money_to_pay",
            "payment_type",
            "session_url",
            "created_at",
        )
        read_only_fields = (
            "id",
            "status",
            "money_to_pay",
            "payment_type",
            "session_url",
            "created_at",
        )
