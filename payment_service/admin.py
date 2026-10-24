from django.contrib import admin

from payment_service.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Display Stripe payments in Django Admin."""

    list_display = (
        "id",
        "membership",
        "payment_type",
        "money_to_pay",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "payment_type",
    )
    search_fields = (
        "membership__member__email",
        "session_id",
    )
    readonly_fields = (
        "session_id",
        "session_url",
        "created_at",
    )
