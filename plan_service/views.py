from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework import viewsets, status
from rest_framework.response import Response
from stripe import StripeError

from payment_service.services import PaymentService
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

    @transaction.atomic
    def perform_create(self, serializer):
        """Create a membership plan and synchronize it with Stripe."""
        plan = serializer.save()

        plan.stripe_product_id = PaymentService().create_stripe_product(plan)
        plan.save(update_fields=["stripe_product_id"])

    def destroy(self, request, *args, **kwargs):
        """Archive the related Stripe product and delete the local plan."""
        plan = self.get_object()

        if plan.memberships.exists() or plan.upgrade_payments.exists():
            return Response(
                {
                    "error": (
                        "This plan cannot be deleted because it is used "
                        "by memberships or payments."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            PaymentService().archive_stripe_product(plan)
        except StripeError:
            return Response(
                {
                    "error": (
                        "The plan could not be archived in Stripe. "
                        "The local plan was not deleted."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except ValueError as error:
            return Response(
                {"error": str(error)},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            plan.delete()
        except ProtectedError:
            return Response(
                {
                    "error": (
                        "This plan cannot be deleted because it is still "
                        "referenced by another object."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)
