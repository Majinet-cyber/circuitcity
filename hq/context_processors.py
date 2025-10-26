from billing.models import Subscription  # adjust to your model

def subscription_context(request):
    if not request.user.is_authenticated:
        return {}
    # Replace this logic with however you link user->business->subscription
    business = getattr(request, "active_business", None) or getattr(request.user, "business", None)
    if not business:
        return {}
    sub = Subscription.objects.filter(business=business).order_by("-id").first()
    return {"subscription": sub}


