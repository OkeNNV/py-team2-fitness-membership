from django.core.validators import MinValueValidator
from django.db import models


class Payment(models.Model):
    """Stripe payment for a membership purchase or plan upgrade.

    Attributes:
        status (str): Payment status (PENDING, PAID or EXPIRED).
        payment_type (str): Payment type (MEMBERSHIP_PURCHASE or UPGRADE_FEE).
        membership (Membership): Membership the payment belongs to.
        session_url (str): Stripe checkout session URL.
        session_id (str): Unique Stripe checkout session id.
        money_to_pay (Decimal): Amount to pay in USD.
        created_at (datetime): Timestamp of payment creation.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        EXPIRED = "EXPIRED", "Expired"

    class Type(models.TextChoices):
        MEMBERSHIP_PURCHASE = "MEMBERSHIP_PURCHASE", "Membership purchase"
        UPGRADE_FEE = "UPGRADE_FEE", "Upgrade fee"

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    payment_type = models.CharField(max_length=20, choices=Type.choices)
    membership = models.ForeignKey(
        "membership.Membership",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    session_url = models.URLField(max_length=2000)
    session_id = models.CharField(max_length=255, unique=True)
    money_to_pay = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(0)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.payment_type} {self.money_to_pay} ({self.status})"
