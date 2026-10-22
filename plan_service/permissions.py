from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Allows reading for all users.
    Create, update and delete only for staff
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)
