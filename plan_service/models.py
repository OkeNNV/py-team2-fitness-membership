from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class MembershipPlan(models.Model):
    """Membership plan offered by the fitness club.

    Attributes:
        name (str): Human-readable plan name.
        code (str): Unique slug identifying the plan.
        duration_days (int): Plan validity period in days.
        price (Decimal): Plan price in USD.
        tier (str): Plan tier (BASIC, STANDARD or PREMIUM).
    """

    class Tier(models.TextChoices):
        BASIC = "BASIC", "Basic"
        STANDARD = "STANDARD", "Standard"
        PREMIUM = "PREMIUM", "Premium"

    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=50, unique=True)
    duration_days = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(730)]
    )
    price = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    tier = models.CharField(max_length=10, choices=Tier.choices)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} ({self.code})"
