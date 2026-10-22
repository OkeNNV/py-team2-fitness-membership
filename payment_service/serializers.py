from rest_framework import serializers

from payment_service.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    """Serialize payment details for API responses.

    All fields are read-only because payments are created and updated
    by the payment workflow rather than directly through the API.
    """

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
