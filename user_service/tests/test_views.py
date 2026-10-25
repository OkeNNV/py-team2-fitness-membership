from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()

REGISTER_URL = reverse("user_service:create")  # приклад: app_name:name
MANAGE_URL = reverse("user_service:manage_user")


class PublicUserApiTests(APITestCase):
    """Test public API endpoints (registration)."""

    def test_create_user_success(self):
        """Test that a user can be successfully registered via API."""
        payload = {
            "email": "newuser@example.com",
            "password": "securepassword123",
            "first_name": "Test",
            "last_name": "User",
        }
        response = self.client.post(REGISTER_URL, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertNotIn("password", response.data)  # Пароль не повинен повертатися у відповіді

        user = User.objects.get(email=payload["email"])
        self.assertTrue(user.check_password(payload["password"]))
        self.assertTrue(user.is_active)

    def test_create_user_duplicate_email_fails(self):
        """Test that registration with an existing email fails."""
        payload = {
            "email": "duplicate@example.com",
            "password": "securepassword123",
        }
        User.objects.create_user(**payload)

        response = self.client.post(REGISTER_URL, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PrivateUserApiTests(APITestCase):
    """Test private (authenticated) API endpoints (profile management)."""

    def setUp(self):
        """Set up authenticated user."""
        self.user = User.objects.create_user(
            email="testuser@example.com",
            password="oldpassword123",
            first_name="Original",
            last_name="Name",
        )
        self.client.force_authenticate(user=self.user)

    def test_retrieve_user_profile_success(self):
        """Test retrieving authenticated user profile."""
        response = self.client.get(MANAGE_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertEqual(response.data["first_name"], self.user.first_name)
        self.assertNotIn("password", response.data)

    def test_retrieve_user_profile_unauthorized_fails(self):
        """Test that unauthenticated user cannot retrieve profile."""
        self.client.logout()
        response = self.client.get(MANAGE_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_user_profile_success(self):
        """Test updating user profile details."""
        payload = {
            "first_name": "UpdatedName",
            "last_name": "UpdatedLastName",
        }
        response = self.client.patch(MANAGE_URL, payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, payload["first_name"])
        self.assertEqual(self.user.last_name, payload["last_name"])

    def test_change_password_success(self):
        """Test successfully changing password via profile update."""
        payload = {
            "old_password": "oldpassword123",
            "new_password": "brandnewpassword456",
        }
        response = self.client.patch(MANAGE_URL, payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("brandnewpassword456"))