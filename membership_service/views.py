from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone

import django_filters
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    inline_serializer,
    extend_schema,
)
from rest_framework import filters, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from stripe import StripeError

from membership_service.models import Membership
from membership_service.serializers import (
    MembershipCreateSerializer,
    MembershipFreezeSerializer,
    MembershipSerializer,
    MembershipUpgradeSerializer,
)
from payment_service.models import Payment
from payment_service.services import PaymentService
from payment_service.serializers import PaymentSerializer

from notification_service.services import (
    notify_membership_created,
    notify_membership_frozen,
)


class IsOwnerOrStaff(permissions.BasePermission):
    """Permission allowing owners to manage their memberships or staff to manage all."""

    def has_object_permission(self, request, view, obj):
        """Check if user is staff or the owner of the membership object."""
        if request.user.is_staff:
            return True
        return obj.member == request.user


class MembershipFilter(django_filters.FilterSet):
    """Custom filter set to support member_id filtering for staff."""

    member_id = django_filters.NumberFilter(field_name="member__id")
    status = django_filters.CharFilter(field_name="status")
    auto_renew = django_filters.BooleanFilter(field_name="auto_renew")

    class Meta:
        """Meta options for MembershipFilter."""

        model = Membership
        fields = ["status", "auto_renew", "member_id"]


@extend_schema(tags=["Memberships"])
class MembershipViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet for managing membership lifecycles (purchase, freeze, resume, upgrade, list)."""

    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = MembershipFilter
    ordering_fields = ["start_date", "end_date"]

    def get_queryset(self):
        """Retrieve memberships based on user role and apply date range filters."""
        if getattr(self, "swagger_fake_view", False):
            return Membership.objects.none()

        user = self.request.user
        qs = Membership.objects.select_related(
            "member", "plan"
        ).prefetch_related("payments")

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
        description=(
                "Creates a membership and returns its Stripe Checkout payment session."
        ),
        request=MembershipCreateSerializer,
        responses={
            201: inline_serializer(
                name="MembershipPurchaseResponse",
                fields={
                    "membership": MembershipSerializer(read_only=True),
                    "payment": PaymentSerializer(read_only=True),
                },
            ),
            400: OpenApiResponse(
                description=(
                    "Validation error, invalid plan, or the user already "
                    "has an active/frozen membership."
                )
            ),
        },
    )
    def create(self, request, *args, **kwargs):
        """Create a membership and return its Stripe payment session."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = serializer.validated_data["plan"]
        today = date.today()
        end_date = today + timedelta(days=plan.duration_days)

        with transaction.atomic():
            membership = serializer.save(
                member=request.user,
                start_date=today,
                end_date=end_date,
                status=Membership.Status.FROZEN,
                price_at_purchase=plan.price,
            )

            payment = PaymentService().create_checkout_session(membership)

        notify_membership_created(membership)

        response_data = {
            "membership": MembershipSerializer(
                membership,
                context=self.get_serializer_context(),
            ).data,
            "payment": PaymentSerializer(payment).data,
        }

        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="List or filter memberships",
        description=(
                "Returns a list of memberships. Regular users see only their own, "
                "while staff members can view all and filter by member_id, "
                "status, auto_renew, and date ranges."
        ),
        parameters=[
            OpenApiParameter(
                name="from",
                description="Filter memberships starting "
                            "on or after this date (YYYY-MM-DD)",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="to",
                description="Filter memberships ending "
                            "on or before this date (YYYY-MM-DD)",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="status",
                description="Filter by status (ACTIVE, EXPIRED, FROZEN)",
                required=False,
                type=str,
            ),
            OpenApiParameter(
                name="member_id",
                description="Filter by member ID (Staff only)",
                required=False,
                type=int,
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        """Return a filtered list of memberships."""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Retrieve membership details",
        description=(
                "Returns detailed information about a specific membership, "
                "including associated plans and payment history."
        ),
    )
    def retrieve(self, request, *args, **kwargs):
        """Return details for a specific membership instance."""
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Freeze a membership",
        description=(
                "Freezes an active membership within its validity window. "
                "Accepts freeze end date via query parameter 'to'."
        ),
        parameters=[
            OpenApiParameter(
                name="to",
                description="Freeze end date (YYYY-MM-DD)",
                required=False,
                type=str
            ),
        ],
        request=None,
        responses={
            200: MembershipSerializer,
            400: OpenApiResponse(
                description=(
                    "Invalid date range, max 30 days exceeded, "
                    "or already frozen."
                )
            ),
        },
    )
    @action(detail=True, methods=["post"])
    def freeze(self, request, pk=None):
        """Process freeze action on an active membership."""
        print("if membership freeze() init")
        membership = Membership.objects.get(pk=pk)
        print(membership.id, membership.end_date, membership.frozen_from, membership.frozen_to)
        if membership.status != Membership.Status.ACTIVE:
            return Response(
                {"error": "Only active memberships can be frozen."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        print(f"membersip was frozen: {membership.was_frozen}")
        print(f"membership frozen from: {membership.frozen_from}")
        if membership.was_frozen:
            print("was frozen")
            return Response(
                {
                    "error": (
                        "This membership has already been frozen "
                        "(allowed only once)."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        frozen_from = timezone.localdate()
        frozen_to_str = request.query_params.get("to") or request.data.get("frozen_to")

        serializer = MembershipFreezeSerializer(
            data={"frozen_from": frozen_from, "frozen_to": frozen_to_str}
        )
        serializer.is_valid(raise_exception=True)

        frozen_to = serializer.validated_data["frozen_to"]

        if not (membership.start_date <= frozen_from <= membership.end_date):
            return Response(
                {
                    "error": (
                        "Freeze dates are outside the membership validity period."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        freeze_days = (frozen_to - frozen_from).days
        new_end_date = membership.end_date + timedelta(days=freeze_days)

        if membership.auto_renew:
            try:
                PaymentService().update_subscription_trial_end(
                    membership=membership,
                    new_billing_date=new_end_date,
                )
            except ValueError as error:
                return Response(
                    {"error": str(error)},
                    status=status.HTTP_409_CONFLICT,
                )
            except StripeError:
                return Response(
                    {
                        "error": (
                            "The Stripe billing date could not be updated. "
                            "The membership was not frozen."
                        )
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        membership.status = Membership.Status.FROZEN
        membership.frozen_from = frozen_from
        membership.frozen_to = frozen_to
        membership.end_date = new_end_date
        membership.save(
            update_fields=[
                "status",
                "frozen_from",
                "frozen_to",
                "end_date",
            ]
        )

        notify_membership_frozen(membership)

        return Response(
            MembershipSerializer(membership).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Resume a frozen membership",
        description=(
                "Unfreezes a currently frozen membership and sets its status "
                "back to ACTIVE."
        ),
        request=None,
        responses={
            200: MembershipSerializer,
            400: OpenApiResponse(
                description="Membership is not in FROZEN state."
            ),
        },
    )
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Process resume action on a frozen membership."""
        membership = Membership.objects.get(pk=pk)

        if membership.status != Membership.Status.FROZEN:
            return Response(
                {"error": "Membership is not currently frozen."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_paid_purchase = membership.payments.filter(
            payment_type=Payment.Type.MEMBERSHIP_PURCHASE,
            status=Payment.Status.PAID,
        ).exists()

        if not has_paid_purchase:
            return Response(
                {"error": "Membership payment has not been completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = date.today()

        if membership.frozen_from and membership.frozen_to and today < membership.frozen_to:
            actual_freeze_start = max(membership.frozen_from, today)
            unused_days = (membership.frozen_to - actual_freeze_start).days
            if unused_days > 0:
                membership.end_date -= timedelta(days=unused_days)

        membership.status = Membership.Status.ACTIVE
        membership.save(
            update_fields=["status", "frozen_from", "frozen_to", "end_date"]
        )

        return Response(
            MembershipSerializer(membership).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Create a membership upgrade payment",
        description=(
                "Creates a Stripe Checkout session for upgrading "
                "the membership to a more expensive plan."
        ),
        request=None,
        parameters=[
            OpenApiParameter(name="plan_id", description="New plan ID", required=False, type=int),
        ],
        responses={
            201: PaymentSerializer,
            400: OpenApiResponse(
                description=(
                    "Invalid target plan, unpaid membership, "
                    "or no payable upgrade period."
                )
            ),
        },
    )
    @action(detail=True, methods=["post"])
    def upgrade(self, request, pk=None):
        """Process plan upgrade for an existing membership."""
        membership = self.get_object()

        if membership.status not in {
            Membership.Status.ACTIVE,
            Membership.Status.FROZEN,
        }:
            return Response(
                {
                    "error": (
                        "Only active or frozen memberships can be upgraded."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan_id = request.query_params.get("plan_id") or request.data.get("plan_id")

        serializer = MembershipUpgradeSerializer(data={"plan_id": plan_id})
        serializer.is_valid(raise_exception=True)

        new_plan = serializer.validated_data["new_plan"]

        if new_plan.price <= membership.plan.price:
            return Response(
                {
                    "error": (
                        "Upgrade is only allowed to a plan with a higher price."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
                membership.auto_renew
                and new_plan.duration_days != membership.plan.duration_days
        ):
            return Response(
                {
                    "error": (
                        "Auto-renew membership can only be upgraded "
                        "to a plan with the same duration."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_paid_purchase = membership.payments.filter(
            payment_type=Payment.Type.MEMBERSHIP_PURCHASE,
            status=Payment.Status.PAID,
        ).exists()

        if not has_paid_purchase:
            return Response(
                {
                    "error": (
                        "The initial membership payment must be completed "
                        "before upgrading."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = date.today()
        remaining_days = max(
            0,
            (membership.end_date - today).days,
        )

        current_duration = max(1, membership.plan.duration_days)
        new_duration = max(1, new_plan.duration_days)

        current_daily_rate = Decimal(membership.plan.price) / Decimal(current_duration)
        new_daily_rate = Decimal(new_plan.price) / Decimal(new_duration)

        upgrade_fee = (new_daily_rate - current_daily_rate) * Decimal(remaining_days)
        upgrade_fee = upgrade_fee.quantize(Decimal("0.01"))

        if upgrade_fee <= 0:
            return Response(
                {"error": "There is no payable upgrade period remaining."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = PaymentService().create_upgrade_checkout_session(
            membership=membership,
            new_plan=new_plan,
            upgrade_fee=upgrade_fee,
        )

        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="cancel-renewal",
    )
    def cancel_renewal(self, request, pk=None):
        """Cancel automatic renewal at the end of the paid period."""
        membership = self.get_object()

        if not membership.auto_renew:
            return Response(
                {
                    "message": (
                        "Automatic renewal is already disabled."
                    )
                },
                status=status.HTTP_200_OK,
            )

        try:
            PaymentService().cancel_subscription_at_period_end(
                membership
            )
        except ValueError as error:
            return Response(
                {"error": str(error)},
                status=status.HTTP_409_CONFLICT,
            )
        except StripeError:
            return Response(
                {
                    "error": (
                        "Automatic renewal could not be disabled "
                        "in Stripe."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        membership.auto_renew = False
        membership.save(update_fields=["auto_renew"])

        return Response(
            MembershipSerializer(membership).data,
            status=status.HTTP_200_OK,
        )
