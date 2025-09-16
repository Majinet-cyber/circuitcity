# audit/utils.py
def audit(request, action: str, obj, message: str = ""):
    from .models import AuditLog
    biz = getattr(request, "business", None)
    AuditLog.objects.create(
        business=biz,
        user=getattr(request, "user", None) if getattr(request, "user", None).is_authenticated else None,
        entity=obj.__class__.__name__,
        entity_id=str(getattr(obj, "pk", "")),
        action=action,
        message=message or "",
        ip=request.META.get("REMOTE_ADDR"),
        ua=request.META.get("HTTP_USER_AGENT", ""),
    )
