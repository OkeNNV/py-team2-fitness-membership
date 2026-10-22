from membership_service.models import Membership
from payment_service.models import Payment


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
