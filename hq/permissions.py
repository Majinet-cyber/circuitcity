from django.contrib.auth.decorators import user_passes_test

def is_hq_admin(user):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name="platform_admin").exists())

hq_admin_required = user_passes_test(is_hq_admin, login_url="/accounts/login/")


