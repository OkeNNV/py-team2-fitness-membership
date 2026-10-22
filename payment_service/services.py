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
    initializes a one-time Stripe Checkout Session, and stores the
    resulting session ID and payment URL in the Payment.

    Args:
        membership: Membership for which the payment is being created.

    Returns:
        The created Payment containing the Stripe session details.

    Raises:
        stripe.StripeError: If Stripe fails to create the Checkout Session.
    """
