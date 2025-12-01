# audit/middleware.py
"""
Middleware for automatically logging important actions to the audit log.
"""
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from .utils import log_audit


class AuditLogMiddleware(MiddlewareMixin):
    """
    Automatically log accesses to important HQ and business views.
    """
    
    # URL patterns that should be logged
    LOGGED_PATTERNS = [
        '/hq/',
        '/wallet/admin/',
        '/admin/',
        '/tenants/manager/',
        '/billing/',
        '/support/hq/',
    ]
    
    # Actions that should be excluded (too noisy)
    EXCLUDED_PATTERNS = [
        '/static/',
        '/media/',
        '/favicon.ico',
        '/api/geo-ping',  # Too frequent
    ]
    
    def process_response(self, request, response):
        """Log the request after it completes successfully."""
        # Only log for authenticated users
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return response
        
        # Skip excluded patterns
        path = request.path
        for pattern in self.EXCLUDED_PATTERNS:
            if path.startswith(pattern):
                return response
        
        # Only log specific patterns
        should_log = any(path.startswith(pattern) for pattern in self.LOGGED_PATTERNS)
        if not should_log:
            return response
        
        # Only log successful responses (2xx, 3xx)
        if response.status_code >= 400:
            return response
        
        # Determine action type
        action = self._get_action_type(request)
        
        # Log it
        try:
            log_audit(
                request=request,
                action=action,
                entity='view_access',
                entity_id=path,
                message=f"Accessed {path}"
            )
        except Exception:
            # Never break the response due to audit logging
            pass
        
        return response
    
    def _get_action_type(self, request):
        """Determine the action type based on the request method."""
        method = request.method.upper()
        
        if method == 'GET':
            if 'export' in request.path.lower() or 'download' in request.path.lower():
                return 'EXPORT'
            return 'VIEW'
        elif method in ['POST', 'PUT', 'PATCH']:
            return 'UPDATE'
        elif method == 'DELETE':
            return 'DELETE'
        else:
            return 'ACCESS'

