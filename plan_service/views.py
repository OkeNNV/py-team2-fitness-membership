from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from rest_framework import viewsets

from payment_service.services import PaymentService
from plan_service.models import MembershipPlan
from plan_service.permissions import IsAdminOrReadOnly
from plan_service.serializers import MembershipPlanSerializer


class MembershipPlanViewSet(viewsets.ModelViewSet):
    """ViewSet for managing MembershipPlan model CRUD endpoints."""

    queryset = MembershipPlan.objects.all()
    serializer_class = MembershipPlanSerializer
    permission_classes = [IsAdminOrReadOnly]

    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["tier"]

    def get_queryset(self):
        """Optionally filter membership plans by tier via query parameter."""
        queryset = super().get_queryset()
        tier_param = self.request.query_params.get("tier")

        if tier_param:
            queryset = queryset.filter(tier__iexact=tier_param)

        return queryset

    @transaction.atomic
    def perform_create(self, serializer):
        """Create a membership plan and synchronize it with Stripe."""
        plan = serializer.save()

        plan.stripe_product_id = PaymentService().create_stripe_product(plan)
        plan.save(update_fields=["stripe_product_id"])
