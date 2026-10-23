from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from user_service.serializers import CustomTokenObtainPairSerializer, CustomTokenRefreshSerializer
from user_service.views import CreateUserView, ManageUserView

app_name = "user_service"

urlpatterns = [
    path("", CreateUserView.as_view(), name="create"),
    path("me/", ManageUserView.as_view(), name="manage_user"),
    path(
        "api/users/token/",
        TokenObtainPairView.as_view(serializer_class=CustomTokenObtainPairSerializer),
        name="token_obtain_pair"
    ),
    path(
        "api/users/token/refresh/",
        TokenRefreshView.as_view(serializer_class=CustomTokenRefreshSerializer),
        name="token_refresh"
    ),
]
