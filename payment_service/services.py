from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from stripe import StripeClient

from config import settings
from membership_service.models import Membership
from payment_service.models import Payment
from plan_service.models import MembershipPlan


class PaymentService:
    """Handle Stripe operations and payment state changes."""

    def __init__(self, stripe_client: StripeClient | None = None):
        self.stripe_client = stripe_client
        if self.stripe_client is None:
            self.stripe_client = StripeClient(settings.STRIPE_SECRET_KEY)

    def construct_webhook_event(
        self,
        payload: bytes,
        signature: str,
    ):
        """Validate and construct a Stripe webhook event."""
        return self.stripe_client.construct_event(
            payload,
            signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )

    def create_stripe_product(
        self,
        plan: MembershipPlan,
    ) -> str:
        """Create a Stripe Product and its prices for a membership plan.

        Creates one one-time price and one recurring price associated with
        the Stripe Product.

        Args:
            plan: Membership plan whose name, price, and duration are used
                to configure the Stripe objects.

        Returns:
            The identifier of the created Stripe Product.

        Raises:
            stripe.StripeError: If Stripe fails to create the product or
                either of its prices.
        """
        product = self.stripe_client.v1.products.create(
            {
                "name": plan.name,
            }
        )

        product_id = product.id
        self.stripe_client.v1.prices.create({
            "currency": "usd",
            "unit_amount": int(plan.price * 100),
            "product": product_id,
            "nickname": "one-time-price",
        })
        self.stripe_client.v1.prices.create({
            "currency": "usd",
            "unit_amount": int(plan.price * 100),
            "recurring": {
                "interval": "day",
                "interval_count": plan.duration_days,
            },
            "product": product_id,
            "nickname": "recurring-price",
        })

        return product_id

    @transaction.atomic
    def create_checkout_session(
        self,
        membership: Membership,
    ) -> Payment:
        """Create or reuse a Checkout Session for a membership purchase.

        Creates a pending Payment associated with the given membership,
        initializes Stripe Checkout Session, and stores the
        resulting session ID and payment URL in the Payment.

        Args:
            membership: Membership for which the payment is being created.

        Returns:
            A new or reusable pending Payment with Stripe session details.

        Raises:
            stripe.StripeError: If a Stripe operation fails.
            ValueError: If the membership is already paid or its Stripe price
                configuration is invalid.
        """
        membership = Membership.objects.select_for_update().get(
            pk=membership.pk
        )

        membership_payments = Payment.objects.filter(
            membership=membership,
            payment_type=Payment.Type.MEMBERSHIP_PURCHASE,
        )
        if membership_payments.filter(status=Payment.Status.PAID).exists():
            raise ValueError("Membership has already been paid")

        pending_payment = (
            membership_payments
            .filter(status=Payment.Status.PENDING)
            .order_by("-created_at")
            .first()
        )
        if pending_payment:
            existing_session = (
                self.stripe_client.v1.checkout.sessions.retrieve(
                    pending_payment.session_id
                )
            )
            if existing_session.status in {"open", "complete"}:
                return pending_payment
            if existing_session.status == "expired":
                pending_payment.status = Payment.Status.EXPIRED
                pending_payment.save(update_fields=["status"])

        stripe_product_id = membership.plan.stripe_product_id
        price_type = "recurring" if membership.auto_renew else "one_time"
        checkout_mode = "subscription" if membership.auto_renew else "payment"

        prices = self.stripe_client.v1.prices.list(
            {
                "product": stripe_product_id,
                "active": True,
                "type": price_type,
            }
        )

        if not prices.data:
            raise ValueError(
                f"No active {price_type} price found "
                f"for Stripe product {stripe_product_id}"
            )

        if len(prices.data) > 1:
            raise ValueError(
                f"Multiple active {price_type} prices found "
                f"for Stripe product {stripe_product_id}"
            )

        price = prices.data[0]
        expected_amount = int(
            membership.price_at_purchase * Decimal("100")
        )

        if price.unit_amount != expected_amount:
            raise ValueError(
                "Membership price does not match Stripe price"
            )

        if price.currency != "usd":
            raise ValueError(
                "Stripe price currency must be USD"
            )

        price_id = price.id

        session = self.stripe_client.v1.checkout.sessions.create(
            {
                "success_url": "http://localhost:8000/payments/success/",
                "cancel_url": "http://localhost:8000/payments/cancel/",
                "line_items": [{"price": price_id, "quantity": 1}],
                "mode": checkout_mode,
                "metadata": {
                    "membership_id": str(membership.id),
                },
            }
        )

        return Payment.objects.create(
            membership=membership,
            payment_type=Payment.Type.MEMBERSHIP_PURCHASE,
            money_to_pay=membership.price_at_purchase,
            session_id=session.id,
            session_url=session.url,
        )

    @transaction.atomic
    def create_upgrade_checkout_session(
        self,
        membership: Membership,
        new_plan: MembershipPlan,
        upgrade_fee: Decimal,
    ) -> Payment:
        """Create or reuse a Stripe Checkout Session for an upgrade fee."""
        membership = (
            Membership.objects
            .select_for_update()
            .select_related("plan")
            .get(pk=membership.pk)
        )

        if new_plan.price <= membership.plan.price:
            raise ValueError(
                "Upgrade is only allowed to a more expensive plan"
            )

        upgrade_fee = upgrade_fee.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        if upgrade_fee <= 0:
            raise ValueError(
                "Upgrade fee must be greater than zero"
            )

        pending_payment = (
            Payment.objects
            .select_for_update()
            .filter(
                membership=membership,
                payment_type=Payment.Type.UPGRADE_FEE,
                status=Payment.Status.PENDING,
            )
            .order_by("-created_at")
            .first()
        )

        if pending_payment:
            existing_session = (
                self.stripe_client.v1.checkout.sessions.retrieve(
                    pending_payment.session_id
                )
            )

            existing_target_plan_id = (
                existing_session.metadata.get("target_plan_id")
            )

            if existing_session.status in {"open", "complete"}:
                if existing_target_plan_id != str(new_plan.id):
                    raise ValueError(
                        "Another upgrade payment is already pending"
                    )

                return pending_payment

            if existing_session.status == "expired":
                pending_payment.status = Payment.Status.EXPIRED
                pending_payment.save(update_fields=["status"])

        stripe_product_id = new_plan.stripe_product_id

        metadata = {
            "membership_id": str(membership.id),
            "target_plan_id": str(new_plan.id),
            "payment_type": Payment.Type.UPGRADE_FEE,
        }

        session = self.stripe_client.v1.checkout.sessions.create(
            {
                "success_url": "http://localhost:8000/payments/success/",
                "cancel_url": "http://localhost:8000/payments/cancel/",
                "mode": "payment",
                "line_items": [
                    {
                        "price_data": {
                            "currency": "usd",
                            "product": stripe_product_id,
                            "unit_amount": int(upgrade_fee * 100),
                        },
                        "quantity": 1,
                    }
                ],
                "metadata": metadata,
            }
        )

        return Payment.objects.create(
            membership=membership,
            target_plan=new_plan,
            payment_type=Payment.Type.UPGRADE_FEE,
            money_to_pay=upgrade_fee,
            session_id=session.id,
            session_url=session.url,
        )

    @transaction.atomic
    def mark_payment_as_paid_and_membership_as_active(self, session_id: str) -> Payment:
        """Mark a payment as paid and apply its membership changes."""
        payment = (
            Payment.objects
            .select_for_update()
            .select_related("target_plan")
            .get(session_id=session_id)
        )

        if payment.status == Payment.Status.PAID:
            return payment

        if payment.status != Payment.Status.PENDING:
            raise ValueError(
                f"Payment cannot be completed from status {payment.status}"
            )

        membership = Membership.objects.select_for_update().get(
            pk=payment.membership_id,
        )

        if payment.payment_type == Payment.Type.MEMBERSHIP_PURCHASE:

            membership.status = Membership.Status.ACTIVE
            membership.save(update_fields=["status"])

        elif payment.payment_type == Payment.Type.UPGRADE_FEE:
            if payment.target_plan is None:
                raise ValueError(
                    "Upgrade payment does not have a target plan"
                )

            membership.plan = payment.target_plan
            membership.save(update_fields=["plan"])

        else:
            raise ValueError(
                f"Unsupported payment type: {payment.payment_type}"
            )

        payment.status = Payment.Status.PAID
        payment.save(update_fields=["status"])

        return payment

    @transaction.atomic
    def mark_payment_as_expired(self, session_id: str) -> Payment:
        """Mark a pending payment as expired using its Stripe session ID."""
        payment = Payment.objects.select_for_update().get(
            session_id=session_id
        )

        if payment.status == Payment.Status.EXPIRED:
            return payment

        if payment.status == Payment.Status.PAID:
            return payment

        payment.status = Payment.Status.EXPIRED
        payment.save(update_fields=["status"])

        return payment
