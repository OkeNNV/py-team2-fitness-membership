from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, F

from django.conf import settings


class Membership(models.Model):
    """Membership of a member for a specific plan and period.

    Attributes:
        member (User): Owner of the membership.
        plan (MembershipPlan): Purchased membership plan.
        start_date (date): Date the membership starts.
        end_date (date): Date the membership ends, shifted by frozen days.
        status (str): Current status (ACTIVE, EXPIRED or FROZEN).
        auto_renew (bool): Whether a new membership is created after expiration.
        price_at_purchase (Decimal): Plan price in USD at the moment of purchase.
        frozen_from (date | None): Start date of the freeze, null if never frozen.
        frozen_to (date | None): End date of the freeze, null if never frozen.
    """

    @property
    def was_frozen(self) -> bool:
        """Return True if the membership has already been frozen."""
        return self.frozen_from is not None

    @property
    def frozen_days(self) -> int:
        """Return the number of days the membership was frozen."""
        if not self.was_frozen:
            return 0
        return (self.frozen_to - self.frozen_from).days

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        FROZEN = "FROZEN", "Frozen"

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    plan = models.ForeignKey(
        "plans.MembershipPlan",
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    auto_renew = models.BooleanField(default=False)
    price_at_purchase = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    frozen_from = models.DateField(null=True, blank=True)
    frozen_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["member"],
                condition=Q(status__in=["ACTIVE", "FROZEN"]),
                name="unique_active_or_frozen_membership_per_member",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="membership_end_date_gte_start_date",
            ),
            models.CheckConstraint(
                condition=(
                    Q(frozen_from__isnull=True, frozen_to__isnull=True)
                    | Q(
                        frozen_from__isnull=False,
                        frozen_to__isnull=False,
                        frozen_to__gte=F("frozen_from"),
                    )
                ),
                name="membership_frozen_range_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "end_date"]),
        ]
