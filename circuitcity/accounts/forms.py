# accounts/forms.py
from django import forms
from .validators import validate_file_size, validate_mime
from .utils.images import process_avatar

class AvatarForm(forms.Form):
    avatar = forms.ImageField(required=True)

    def clean_avatar(self):
        f = self.cleaned_data["avatar"]
        validate_file_size(f)

        # Use browser-provided content_type as a hint (not authoritative)
        ctype = getattr(f, "content_type", "")
        if ctype:
            validate_mime(ctype)

        # Deep validation + re-encode
        try:
            processed = process_avatar(f)
        except Exception:
            raise forms.ValidationError("Could not process image. Use a valid JPEG/PNG/WEBP.")
        return processed
