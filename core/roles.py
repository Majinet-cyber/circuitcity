from django.contrib.auth import get_user_model
User = get_user_model()

def is_manager(user: User) -> bool:
    # Treat staff OR profile flag as manager/admin
    if not user.is_authenticated:
        return False
    try:
        return bool(user.is_staff or getattr(user, "profile", None) and getattr(user.profile, "is_manager", False))
    except Exception:
        return bool(user.is_staff)

def is_agent(user: User) -> bool:
    return user.is_authenticated and not is_manager(user)
