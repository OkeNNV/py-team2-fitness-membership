from rest_framework import viewsets
from plan_service.models import MembershipPlan
from plan_service.permissions import IsAdminOrReadOnly
from plan_service.serializers import MembershipPlanSerializer


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
