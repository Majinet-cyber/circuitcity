# accounts/views.py
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django.conf import settings

from .forms import AvatarForm
from .forms import ForgotPasswordRequestForm, VerifyCodeResetForm
from .utils.reset import create_or_reuse_code, send_reset_code_email, verify_code_and_consume

User = get_user_model()


# ----------------------------
# Helpers
# ----------------------------
def _get_user_by_identifier(identifier: str):
    """
    Prefer username (should be unique). If that fails, resolve by email.
    Email may not be unique in your DB, so choose a deterministic 'best' candidate:
    most recently active (last_login), then most recently created (date_joined), then id.
    """
    ident = (identifier or "").strip()
    if not ident:
        return None

    # 1) Try username exact (case-insensitive)
    try:
        return User.objects.get(username__iexact=ident)
    except User.DoesNotExist:
        pass
    except User.MultipleObjectsReturned:
        # Extremely rare, but handle gracefully
        user = (
            User.objects.filter(username__iexact=ident)
            .order_by("-last_login", "-date_joined", "-id")
            .first()
        )
        if user:
            return user

    # 2) Fall back to email (may have duplicates)
    user = (
        User.objects.filter(email__iexact=ident)
        .order_by("-last_login", "-date_joined", "-id")
        .first()
    )
    return user


# ----------------------------
# Avatar upload (self)
# ----------------------------
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

    profile.avatar.save(f.name, f, save=True)
    messages.success(request, "Avatar updated.")
    return redirect(next_url)


# ----------------------------
# Avatar upload (by agent_id)
# ----------------------------
@login_required
@require_POST
def upload_agent_avatar(request, agent_id: int):
    next_url = request.POST.get("next") or "/"

    if not (request.user.is_superuser or request.user.is_staff or request.user.id == agent_id):
        messages.error(request, "You do not have permission to update this avatar.")
        return redirect(next_url)

    form = AvatarForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "; ".join([e for errs in form.errors.values() for e in errs]))
        return redirect(next_url)

    try:
        target = User.objects.get(pk=agent_id)
    except User.DoesNotExist:
        messages.error(request, "Agent not found.")
        return redirect(next_url)

    f = form.cleaned_data["avatar"]
    profile = getattr(target, "profile", None)
    if profile is None:
        from .models import Profile
        profile, _ = Profile.objects.get_or_create(user=target)

    profile.avatar.save(f.name, f, save=True)
    messages.success(request, "Agent avatar updated.")
    return redirect(next_url)


# ----------------------------
# Forgot password: Step 1 (request code)
# ----------------------------
@require_http_methods(["GET", "POST"])
def forgot_password_request(request):
    """
    Accepts email or username, sends a 6-digit code to the user's email if the account exists.
    Always responds with a success message to avoid leaking account existence.
    """
    form = ForgotPasswordRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = _get_user_by_identifier(form.cleaned_data["identifier"])
        if user and user.email:
            code = create_or_reuse_code(user, request.META.get("REMOTE_ADDR"))
            try:
                send_reset_code_email(user, code)
            except Exception:
                # Do not leak details; still claim success
                pass
        messages.success(request, "If an account exists, we’ve emailed a reset code.")
        return redirect("accounts:forgot_password_request")
    return render(request, "accounts/forgot_password_request.html", {"form": form})


# ----------------------------
# Forgot password: Step 2 (verify code + set new password)
# ----------------------------
@require_http_methods(["GET", "POST"])
def forgot_password_reset(request):
    """
    Verifies the provided 6-digit code for the given identifier (email/username),
    and if valid, updates the password.
    """
    form = VerifyCodeResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"]
        user = _get_user_by_identifier(identifier)
        if not user:
            messages.error(request, "Invalid code or identifier.")
            return redirect("accounts:forgot_password_reset")

        code = form.cleaned_data["code"]
        if not verify_code_and_consume(user, code):
            messages.error(request, "Invalid or expired code.")
            return redirect("accounts:forgot_password_reset")

        new_password = form.cleaned_data["new_password1"]
        user.set_password(new_password)
        user.save()
        try:
            update_session_auth_hash(request, user)
        except Exception:
            pass

        messages.success(request, "Password updated. You can now sign in.")
        return redirect(getattr(settings, "LOGIN_URL", "login"))

    return render(request, "accounts/forgot_password_reset.html", {"form": form})
