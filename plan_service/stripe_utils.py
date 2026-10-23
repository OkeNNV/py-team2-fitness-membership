import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_stripe_product_and_price(plan):
    """Create a Product and Price in Stripe for a MembershipPlan instance."""
    product = stripe.Product.create(
        name=plan.name,
        description=f"{plan.tier} plan for {plan.duration_days} days",
    )

    price = stripe.Price.create(
        product=product.id,
        unit_amount=int(plan.price * 100),
        currency="usd",
        recurring={
            "interval": "day",
            "interval_count": plan.duration_days,
        },
    )

    return product.id, price.id
