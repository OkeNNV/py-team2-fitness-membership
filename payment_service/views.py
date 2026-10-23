from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from stripe import SignatureVerificationError

from payment_service.services import PaymentService


@method_decorator(csrf_exempt, name="dispatch")
class StripeWebhookView(View):
    """Receive and process Stripe webhook events."""

    http_method_names = ["post"]

    def post(
        self,
        request: HttpRequest,
        *args,
        **kwargs,
    ) -> HttpResponse:
        """Validate and process a Stripe webhook event."""
        payload = request.body
        signature = request.headers.get("Stripe-Signature")

        if not signature:
            return HttpResponse(status=400)

        if not settings.STRIPE_WEBHOOK_SECRET:
            return HttpResponse(status=500)

        payment_service = PaymentService()

        try:
            event = payment_service.construct_webhook_event(
                payload,
                signature,
            )
        except (ValueError, SignatureVerificationError):
            return HttpResponse(status=400)

        if event.type == "checkout.session.completed":
            session = event.data.object

            if session.payment_status == "paid":
                payment_service.mark_payment_as_paid(session.id)

        elif event.type == "checkout.session.async_payment_succeeded":
            session = event.data.object
            payment_service.mark_payment_as_paid(session.id)

        elif event.type == "checkout.session.expired":
            session = event.data.object
            payment_service.mark_payment_as_expired(session.id)

        return HttpResponse(status=200)
