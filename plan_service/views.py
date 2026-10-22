from rest_framework import viewsets
from .models import MembershipPlan
from .permissions import IsAdminOrReadOnly
from .serializers import MembershipPlanSerializer


class MembershipPlanViewSet(viewsets.ModelViewSet):
    queryset = MembershipPlan.objects.all()
    serializer_class = MembershipPlanSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = super().get_queryset()
        tier_param = self.request.query_params.get("tier")

        if tier_param:
            queryset = queryset.filter(tier__iexact=tier_param)

        return queryset
