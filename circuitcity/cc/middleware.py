import time, uuid, logging
from django.utils.deprecation import MiddlewareMixin
from django.utils import timezone
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("access")

class RequestIDMiddleware(MiddlewareMixin):
    HEADER_NAME = "HTTP_X_REQUEST_ID"
    def process_request(self, request: HttpRequest):
        rid = request.META.get(self.HEADER_NAME) or str(uuid.uuid4())
        request.request_id = rid

class AccessLogMiddleware(MiddlewareMixin):
    def process_request(self, request: HttpRequest):
        request._start_ts = time.perf_counter()

    def process_response(self, request: HttpRequest, response: HttpResponse):
        try:
            latency_ms = int((time.perf_counter() - getattr(request, "_start_ts", time.perf_counter())) * 1000)
            user_id = getattr(getattr(request, "user", None), "id", None)
            logger.info(
                "http_request",
                extra={
                    "ts": timezone.now().isoformat(),
                    "request_id": getattr(request, "request_id", None),
                    "method": getattr(request, "method", None),
                    "path": request.get_full_path() if hasattr(request, "get_full_path") else None,
                    "status": getattr(response, "status_code", None),
                    "latency_ms": latency_ms,
                    "user_id": user_id,
                    "ip": request.META.get("REMOTE_ADDR") if hasattr(request, "META") else None,
                },
            )
        except Exception:
            pass
        return response
