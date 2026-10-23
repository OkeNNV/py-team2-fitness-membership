from stripe import StripeClient

from config import settings
from membership_service.models import Membership
from payment_service.models import Payment
from plan_service.models import MembershipPlan


def create_stripe_product(plan: MembershipPlan) -> str:
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
    client = StripeClient(settings.STRIPE_SECRET_KEY)
    product = client.v1.products.create(
        {
            "name": plan.name,
        }
    )

    product_id = product.id
    client.v1.prices.create({
        "currency": "usd",
        "unit_amount": int(plan.price * 100),
        "product": product_id,
        "nickname": "one-time-price",
    })
    client.v1.prices.create({
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


def create_checkout_session(membership: Membership) -> Payment:
    """Create a Stripe Checkout Session for a membership purchase.

    Creates a pending Payment associated with the given membership,
    initializes Stripe Checkout Session, and stores the
    resulting session ID and payment URL in the Payment.

    Args:
        membership: Membership for which the payment is being created.

    Returns:
        The created Payment containing the Stripe session details.

    Raises:
        stripe.StripeError: If Stripe fails to create the Checkout Session.
        ValueError: If the required price is missing or the number of matching
            prices is unexpected.
    """
    client = StripeClient(settings.STRIPE_SECRET_KEY)

    stripe_product_id = membership.plan.code
    price_type = "recurring" if membership.auto_renew else "one_time"
    checkout_mode = "subscription" if membership.auto_renew else "payment"

    prices = client.v1.prices.list(
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

    price_id = prices.data[0].id

    session = client.v1.checkout.sessions.create(
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
