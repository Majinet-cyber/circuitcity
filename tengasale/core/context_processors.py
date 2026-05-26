from django.conf import settings


def tengasale_support(request):
    return {
        "tengasale_whatsapp_link": settings.TENGASALE_WHATSAPP_LINK,
    }
