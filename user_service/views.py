from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from user_service.serializers import UserSerializer, UserCreateSerializer


class CreateUserView(generics.CreateAPIView):
    """View for creating a new user (registration)."""

    serializer_class = UserCreateSerializer
    permission_classes = ()


class ManageUserView(generics.RetrieveUpdateAPIView):
    """View for retrieving and updating the authenticated user's profile."""

    serializer_class = UserSerializer
    permission_classes = (IsAuthenticated,)

    def get_object(self):
        """Return the currently authenticated user."""
        return self.request.user
