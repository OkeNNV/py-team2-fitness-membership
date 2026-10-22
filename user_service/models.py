from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Manager for the User model that uses email as the unique identifier."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str, **extra_fields) -> User:
        """Create and save a user with the given email and password.

        Args:
            email (str): User email, required.
            password (str | None): Raw password, hashed before saving.
            **extra_fields: Additional User model fields.

        Returns:
            User: The created user.

        Raises:
            ValueError: If the email is not provided.
        """
        if not email:
            raise ValueError("The email must be set")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self, email: str, password: str | None = None, **extra_fields
    ) -> User:
        """Create a regular user without staff or superuser permissions.

        Args:
            email (str): User email.
            password (str | None): Raw password.
            **extra_fields: Additional User model fields.

        Returns:
            User: The created user.
        """
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields) -> User:
        """Create a superuser with staff and superuser permissions.

        Args:
            email (str): User email.
            password (str | None): Raw password.
            **extra_fields: Additional User model fields.

        Returns:
            User: The created superuser.

        Raises:
            ValueError: If is_staff or is_superuser is explicitly set to False.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError(
                "Superuser must have is_staff and is_superuser set to True"
            )
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Club member or staff user authenticated by email.

    Attributes:
        email (str): Unique email used as the login.
        first_name (str): Member first name (inherited).
        last_name (str): Member last name (inherited).
        password (str): Hashed password (inherited).
        is_staff (bool): Whether the user is a club staff member (inherited).
    """

    username = None
    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email
