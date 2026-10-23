from rest_framework import viewsets
from plan_service.models import MembershipPlan
from plan_service.permissions import IsAdminOrReadOnly
from plan_service.serializers import MembershipPlanSerializer
from plan_service.stripe_utils import create_stripe_product_and_price


class MembershipPlanViewSet(viewsets.ModelViewSet):
    """ViewSet for managing MembershipPlan model CRUD endpoints."""

    queryset = MembershipPlan.objects.all()
    serializer_class = MembershipPlanSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        """Optionally filter membership plans by tier via query parameter."""
        queryset = super().get_queryset()
        tier_param = self.request.query_params.get("tier")

        if tier_param:
            queryset = queryset.filter(tier__iexact=tier_param)

        return queryset

    def perform_create(self, serializer):
        """Save instance and generate Stripe product & price IDs."""
        plan = serializer.save()
        try:
            product_id, price_id = create_stripe_product_and_price(plan)
            plan.stripe_product_id = product_id
            plan.stripe_price_id = price_id
            plan.save()
        except Exception as e:
            print(f"Failed to create Stripe product/price: {e}")
