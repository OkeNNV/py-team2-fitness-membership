from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """Permissions for admin write and public read access.

    Allows read-only access to any request (GET, HEAD, OPTIONS).
    Write, update, and delete actions are restricted to staff users.
    """

    def has_permission(self, request, view):
        """Check if the request user has permissions to perform the action."""
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)
