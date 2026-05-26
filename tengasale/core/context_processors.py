from django.conf import settings

from accounts.utils import get_tengasale_role


def tengasale_support(request):
    return {
        "tengasale_whatsapp_link": settings.TENGASALE_WHATSAPP_LINK,
        "current_tengasale_role": get_tengasale_role(request.user),
        "current_user_is_hq": get_tengasale_role(request.user) == "hq",
        "current_user_can_use_django_admin": request.user.is_authenticated
        and (request.user.is_staff or request.user.is_superuser),
    }
