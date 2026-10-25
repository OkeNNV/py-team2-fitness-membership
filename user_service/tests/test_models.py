from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

User = get_user_model()


class UserManagerTests(TestCase):
    """Tests for custom UserManager and User model."""

    def test_create_user(self):
        """Test creating a regular user with an email and password."""
        email = "test@example.com"
        password = "securepassword123"
        user = User.objects.create_user(email=email, password=password)

        self.assertEqual(user.email, email)
        self.assertTrue(user.check_password(password))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertIsNone(user.username)

    def test_normalize_email(self):
        """Test that user email is normalized (domain part is lowercase)."""
        email = "TEST@EXAMPLE.COM"
        user = User.objects.create_user(email=email, password="password123")
        self.assertEqual(user.email, "TEST@example.com")

    def test_create_user_without_email_raises_error(self):
        """Test that creating a user without an email raises ValueError."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="password123")

    def test_create_superuser(self):
        """Test creating a superuser with correct staff and superuser flags."""
        email = "admin@example.com"
        password = "adminpassword123"
        admin_user = User.objects.create_superuser(email=email, password=password)

        self.assertEqual(admin_user.email, email)
        self.assertTrue(admin_user.check_password(password))
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)

    def test_create_superuser_with_invalid_flags_raises_error(self):
        """Test that superuser creation fails if is_staff or is_superuser is False."""
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com",
                password="password123",
                is_staff=False,
            )

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com",
                password="password123",
                is_superuser=False,
            )

    def test_email_is_unique(self):
        """Test that creating two users with the same email raises IntegrityError."""
        email = "duplicate@example.com"
        User.objects.create_user(email=email, password="password123")

        with self.assertRaises(IntegrityError):
            User.objects.create_user(email=email, password="anotherpassword123")

    def test_str_representation(self):
        """Test the string representation of the user model returns the email."""
        email = "string@example.com"
        user = User.objects.create_user(email=email, password="password123")
        self.assertEqual(str(user), email)
