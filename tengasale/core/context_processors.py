from django.conf import settings

from accounts.utils import is_hq


def tengasale_support(request):
    return {
        "tengasale_whatsapp_link": settings.TENGASALE_WHATSAPP_LINK,
        "current_user_is_hq": is_hq(request.user),
    }
