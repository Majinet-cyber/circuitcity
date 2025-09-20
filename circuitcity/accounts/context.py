def role_flags(request):
    u = request.user
    is_auth = u.is_authenticated
    is_admin = is_auth and u.is_staff
    is_manager = is_auth and getattr(u, "is_manager", False)
    is_agent = is_auth and not (is_admin or is_manager)
    return {"is_admin": is_admin, "is_manager": is_manager, "is_agent": is_agent}
