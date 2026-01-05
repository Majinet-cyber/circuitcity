# core/middleware.py
"""
Middleware for request processing and normalization.
"""
from django.http import HttpResponsePermanentRedirect
from django.utils.deprecation import MiddlewareMixin


class NormalizeDoubleSlashMiddleware(MiddlewareMixin):
    """
    Middleware to normalize double slashes in URLs.

    Redirects paths like /settings// to /settings/
    This prevents 404 errors and template crashes from malformed URLs.

    Example:
        /settings// → 301 redirect to /settings/
        /accounts//profile/ → 301 redirect to /accounts/profile/
    """

    def process_request(self, request):
        path = request.path_info

        # Check if path contains double slashes
        if "//" in path:
            # Normalize: replace multiple consecutive slashes with single slash
            normalized_path = path
            while "//" in normalized_path:
                normalized_path = normalized_path.replace("//", "/")

            # Build the full URL with querystring
            full_url = normalized_path
            if request.GET:
                query_string = request.GET.urlencode()
                full_url = f"{normalized_path}?{query_string}"

            # 301 redirect to normalized URL
            return HttpResponsePermanentRedirect(full_url)

        return None
