from django.contrib import admin
from .models import MembershipPlan


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    """Admin configuration for MembershipPlan model."""

    list_display = (
        "name",
        "code",
        "tier",
        "price",
        "duration_days",
    )
    list_filter = (
        "tier",
    )
    search_fields = (
        "name",
        "code",
    )
    prepopulated_fields = {
        "code": ("name",)
    }
