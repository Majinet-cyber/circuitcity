from rest_framework.permissions import BasePermission

class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in ("GET","HEAD","OPTIONS"):
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_staff


