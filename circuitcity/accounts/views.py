# accounts/views.py
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.contrib import messages
from .forms import AvatarForm

@login_required
@require_POST
def upload_my_avatar(request):
    form = AvatarForm(request.POST, request.FILES)
    next_url = request.POST.get("next") or "/"
    if not form.is_valid():
        messages.error(request, "; ".join([e for errs in form.errors.values() for e in errs]))
        return redirect(next_url)

    f = form.cleaned_data["avatar"]
    profile = getattr(request.user, "profile", None)
    if profile is None:
        from .models import Profile
        profile, _ = Profile.objects.get_or_create(user=request.user)

    # Save sanitized image
    profile.avatar.save(f.name, f, save=True)
    messages.success(request, "Avatar updated.")
    return redirect(next_url)
