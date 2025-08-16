from django.conf import settings
from django.db import models

def avatar_upload_to(instance, filename):
    return f"avatars/{instance.pk}/{filename}"

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to=avatar_upload_to, blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_username()} profile"
