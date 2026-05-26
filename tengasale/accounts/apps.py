from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self):
        from django.contrib.auth import get_user_model

        from .models import UserProfile

        User = get_user_model()
        if not hasattr(User, "userprofile"):
            User.userprofile = property(lambda user: user.profile)

        import accounts.signals  # noqa: F401
