def active_scope_ctx(request):
    try:
        _, ctx = resolve_active_context(request)
        return ctx
    except Exception:
        return {}
