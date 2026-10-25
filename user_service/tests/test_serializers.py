from django.contrib.auth import get_user_model
from django.test import TestCase
from user_service.serializers import UserCreateSerializer, UserSerializer

User = get_user_model()


class UserCreateSerializerTests(TestCase):
    """Tests for UserCreateSerializer (registration)."""

    def test_create_user_valid(self):
        """Test that a user can be successfully created with valid data."""
        data = {
            "email": "newuser@example.com",
            "password": "securepassword123",
            "first_name": "John",
            "last_name": "Doe",
        }
        serializer = UserCreateSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        user = serializer.save()

        self.assertEqual(user.email, data["email"])
        self.assertTrue(user.check_password(data["password"]))
        self.assertEqual(user.first_name, data["first_name"])
        self.assertEqual(user.last_name, data["last_name"])
        self.assertTrue(user.is_active)

    def test_password_too_short(self):
        """Test validation error when password is shorter than min_length (5)."""
        data = {
            "email": "short@example.com",
            "password": "123",  # Less than 5 chars
        }
        serializer = UserCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("password", serializer.errors)

    def test_email_is_required(self):
        """Test validation error when email is missing."""
        data = {
            "password": "securepassword123",
        }
        serializer = UserCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)


class UserSerializerTests(TestCase):
    """Tests for UserSerializer (profile update and password change)."""

    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            email="user@example.com",
            password="oldpassword123",
            first_name="Alice",
            last_name="Smith",
        )

    def test_update_profile_info(self):
        """Test updating user first and last name."""
        data = {
            "first_name": "Alicia",
            "last_name": "Johnson",
        }
        serializer = UserSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        updated_user = serializer.save()

        self.assertEqual(updated_user.first_name, "Alicia")
        self.assertEqual(updated_user.last_name, "Johnson")
        self.assertEqual(updated_user.email, "user@example.com")  # Email unchanged

    def test_change_password_success(self):
        """Test successfully changing the password with correct old password."""
        data = {
            "old_password": "oldpassword123",
            "new_password": "newsecurepassword456",
        }
        serializer = UserSerializer(self.user, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newsecurepassword456"))
        self.assertFalse(self.user.check_password("oldpassword123"))

    def test_change_password_wrong_old_password(self):
        """Test error when old password is incorrect during change."""
        data = {
            "old_password": "wrongpassword",
            "new_password": "newsecurepassword456",
        }
        serializer = UserSerializer(self.user, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn("old_password", serializer.errors)

    def test_change_password_missing_old_password(self):
        """Test error when new password is provided but old password is missing."""
        data = {
            "new_password": "newsecurepassword456",
        }
        serializer = UserSerializer(self.user, data=data, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn("old_password", serializer.errors)
