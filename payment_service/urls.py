from django.urls import path

from payment_service.views import StripeWebhookView


app_name = "payment_service"

urlpatterns = [
    path(
        "webhook/",
        StripeWebhookView.as_view(),
        name="stripe-webhook",
    ),
]
