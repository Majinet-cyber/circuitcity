from .models import BusinessSetting


def get_business_settings():
    settings, _ = BusinessSetting.objects.get_or_create(pk=1)
    return settings
