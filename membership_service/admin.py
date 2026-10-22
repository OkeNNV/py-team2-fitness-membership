from django.contrib import admin

from membership_service.models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    """Admin for Membership model."""

    list_display = ["id", "member", "plan", "status", "start_date", "end_date", "auto_renew"]
    list_filter = ["status", "auto_renew"]
    search_fields = ["member__email", "plan__name"]
