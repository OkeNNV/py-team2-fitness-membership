from datetime import date, timedelta
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiResponse
)

from membership_service.models import Membership
from membership_service.serializers import (
    MembershipSerializer,
    MembershipCreateSerializer,
    MembershipFreezeSerializer,
)
from plan_service.models import MembershipPlan


class IsOwnerOrStaff(permissions.BasePermission):
    """Permission allowing owners to manage their memberships or staff to manage all."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.member == request.user


@extend_schema(tags=["Memberships"])
class MembershipViewSet(viewsets.ModelViewSet):
    """ViewSet for managing membership lifecycles (purchase, freeze, resume, upgrade, list)."""
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["status", "auto_renew", "member"]
    ordering_fields = ["start_date", "end_date"]

    def get_queryset(self):
        """Retrieve memberships based on user role and apply date range filters."""
        user = self.request.user
        qs = Membership.objects.select_related("member", "plan")

        # .prefetch_related("payments")

        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")
        if date_from:
            qs = qs.filter(start_date__gte=date_from)
        if date_to:
            qs = qs.filter(end_date__lte=date_to)

        if user.is_staff:
            return qs
        return qs.filter(member=user)

    def get_serializer_class(self):
        """Return appropriate serializer class depending on the action."""
        if self.action == "create":
            return MembershipCreateSerializer
        return MembershipSerializer

    @extend_schema(
        summary="Purchase a new membership",
        description="Creates a new membership for the authenticated user",
        responses={201: MembershipSerializer, 400: OpenApiResponse(
            description="Validation error or user already has an active/frozen membership.")}
    )
    def perform_create(self, serializer):
        plan_id = serializer.validated_data.get("plan_id")
        auto_renew = serializer.validated_data.get("auto_renew", False)
        plan = MembershipPlan.objects.get(id=plan_id)

        today = date.today()
        end_date = today + timedelta(days=plan.duration_days)

        serializer.save(
            member = self.request.user,
            plan = plan,
            start_date = today,
            end_date = end_date,
            status = Membership.Status.ACTIVE,
            auto_renew = auto_renew,
            price_at_purchase = plan.price,
        )

    @extend_schema(
        summary="List or filter memberships",
        description="Returns a list of memberships. "
                    "Regular users see only their own, while staff members can view all and filter by "
                    "member_id, status, auto_renew, and date ranges.",
        parameters=[
            OpenApiParameter(name="from", description="Filter memberships starting on or after this date (YYYY-MM-DD)",
                             required=False, type=str),
            OpenApiParameter(name="to", description="Filter memberships ending on or before this date (YYYY-MM-DD)",
                             required=False, type=str),
            OpenApiParameter(name="status", description="Filter by status (ACTIVE, EXPIRED, FROZEN)", required=False,
                             type=str),
            OpenApiParameter(name="member_id", description="Filter by member ID (Staff only)", required=False,
                             type=int),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Retrieve membership details",
        description="Returns detailed information about a specific membership,"
                    " including associated plans and payment history."
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Freeze a membership",
        description="Freezes an active membership within its validity window.",
        request=MembershipFreezeSerializer,
        responses={
            200: MembershipSerializer,
            400: OpenApiResponse(description="Invalid date range, max 30 days exceeded, or already frozen.")
        }
    )
    @action(detail=True, methods=["post"])
    def freeze(self, request, pk=None):
        membership = self.get_object()

        if membership.status != Membership.Status.ACTIVE:
            return Response({"error": "Only active memberships can be frozen."}, status=status.HTTP_400_BAD_REQUEST)

        if membership.was_frozen:
            return Response({"error": "This membership has already been frozen (allowed only once)."},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = MembershipFreezeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        frozen_from = serializer.validated_data["frozen_from"]
        frozen_to = serializer.validated_data["frozen_to"]

        if not (membership.start_date <= frozen_from <= membership.end_date):
            return Response({"error": "Freeze dates are outside the membership validity period."},
                            status=status.HTTP_400_BAD_REQUEST)

        freeze_days = (frozen_to - frozen_from).days + 1

        membership.status = Membership.Status.FROZEN
        membership.frozen_from = frozen_from
        membership.frozen_to = frozen_to
        membership.end_date = membership.end_date + timedelta(days=freeze_days)
        membership.save()

        return Response(MembershipSerializer(membership).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Resume a frozen membership",
        description="Unfreezes a currently frozen membership and sets its status back to ACTIVE.",
        responses={200: MembershipSerializer, 400: OpenApiResponse(description="Membership is not in FROZEN state.")}
    )
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        membership = self.get_object()

        if membership.status != Membership.Status.FROZEN:
            return Response({"error": "Membership is not currently frozen."}, status=status.HTTP_400_BAD_REQUEST)

        membership.status = Membership.Status.ACTIVE
        membership.save()

        return Response(MembershipSerializer(membership).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Upgrade membership plan",
        description="Upgrades an existing membership to a new plan with a higher price/tier.",
        responses={
            200: OpenApiResponse(description="Upgrade successful, returns fee details and updated membership."),
            400: OpenApiResponse(description="New plan must have a higher price/tier.")
        }
    )
    @action(detail=True, methods=["post"])
    def upgrade(self, request, pk=None):
        membership = self.get_object()
        new_plan_id = request.data.get("plan_id")

        if not new_plan_id:
            return Response({"error": "New plan_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_plan = MembershipPlan.objects.get(id=new_plan_id)
        except MembershipPlan.DoesNotExist:
            return Response({"error": "Plan not found."}, status=status.HTTP_404_NOT_FOUND)

        if new_plan.price <= membership.plan.price:
            return Response({"error": "Upgrade is only allowed to a plan with a higher price."},
                            status=status.HTTP_400_BAD_REQUEST)

        today = date.today()
        remaining_days = max(0, (membership.end_date - today).days)

        credit = (membership.plan.price / membership.plan.duration_days) * remaining_days
        new_full_price = (new_plan.price / new_plan.duration_days) * remaining_days
        upgrade_fee = max(0, new_full_price - credit)

        membership.plan = new_plan
        membership.save()

        return Response({
            "message": "Membership successfully upgraded.",
            "upgrade_fee": round(upgrade_fee, 2),
            "membership": MembershipSerializer(membership).data
        }, status=status.HTTP_200_OK)
