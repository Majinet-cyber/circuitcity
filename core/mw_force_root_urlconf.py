# core/mw_force_root_urlconf.py
from django.conf import settings
from django.urls import set_urlconf

class ForceRootURLConf:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Run *last* on the request path so we override any earlier changes
        set_urlconf(settings.ROOT_URLCONF)
        try:
            # avoid accidental scoping to an app
            if hasattr(request, "current_app"):
                request.current_app = None
        except Exception:
            pass

        response = self.get_response(request)

        # clean up after response
        set_urlconf(None)
        return response


