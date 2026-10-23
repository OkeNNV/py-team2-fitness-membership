from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user profile management and password changing."""

    old_password = serializers.CharField(
        required=False,
        write_only=True,
        style={"input_type": "password"},
        label=_("Old password"),
    )
    new_password = serializers.CharField(
        required=False,
        write_only=True,
        style={"input_type": "password"},
        label=_("New password"),
    )

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "old_password",
            "new_password",
        )
        read_only_fields = ("id", "is_staff")

    def validate(self, attrs):
        """Validate old and new passwords when changing password."""
        old_password = attrs.get("old_password")
        new_password = attrs.get("new_password")

        if old_password or new_password:
            if not old_password:
                raise serializers.ValidationError(
                    {"old_password": _("Old password is required to set a new password.")}
                )
            if not new_password:
                raise serializers.ValidationError(
                    {"new_password": _("New password is required.")}
                )

            user = self.instance
            if user and not user.check_password(old_password):
                raise serializers.ValidationError(
                    {"old_password": _("Wrong old password.")}
                )

            validate_password(new_password, user)

        return attrs

    def update(self, instance, validated_data):
        """Update user profile and optionally change password."""
        validated_data.pop("old_password", None)  # <--- просто видаляємо, без присвоєння у змінну
        new_password = validated_data.pop("new_password", None)

        user = super().update(instance, validated_data)

        if new_password:
            user.set_password(new_password)
            user.save()

        return user


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""

    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        label=_("Password"),
    )

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "password",
            "is_staff",
        )
        read_only_fields = ("id", "is_staff")
        extra_kwargs = {
            "password": {"min_length": 5},
        }

    def validate_password(self, value):
        """Validate password against Django's validators."""
        validate_password(value)
        return value

    def create(self, validated_data):
        """Create user with encrypted password."""
        return get_user_model().objects.create_user(**validated_data)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom serializer for obtaining a pair of JWT access and refresh tokens.

    Customizes the output of access token format to include the 'Token' prefix.
    """

    def validate(self, attrs):
        """Validate credentials and return formatted access and refresh tokens."""
        data = super().validate(attrs)
        return {
            "access token": f"Token {data.get('access')}",
            "refresh token": data.get("refresh"),
        }


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """Custom serializer for refreshing the JWT access token.

    Customizes the output format to include the 'Token' prefix for the new access token.
    """

    def validate(self, attrs):
        """Validate refresh token and return formatted new access and refresh tokens."""
        data = super().validate(attrs)
        return {
            "access token": f"Token {data.get('access')}",
            "refresh": data.get("refresh", attrs.get("refresh")),
        }
