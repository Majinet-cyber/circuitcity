# inventory/middleware.py
from .utils import forbid_auditor_on_write

class AuditorReadOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        forbid_auditor_on_write(request)
        return self.get_response(request)
