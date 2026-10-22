from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import MembershipPlanViewSet

router = DefaultRouter()
router.register(r"plans", MembershipPlanViewSet, basename="membership-plan")

urlpatterns = [
    path("", include(router.urls)),
]
