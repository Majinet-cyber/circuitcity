from django.contrib.auth.decorators import user_passes_test
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.db.models import Q
from django.utils import timezone

from .models import BusinessSubscription


def _is_staff(u):
    return u.is_authenticated and (u.is_staff or u.is_superuser)


@method_decorator(user_passes_test(_is_staff), name="dispatch")
class HQSubscriptionsView(TemplateView):
    """
    Staff-only, global subscriptions list (ignores tenant context).
    """
    template_name = "billing/hq_subscriptions.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        q = (self.request.GET.get("q") or "").strip()

        subs = (
            BusinessSubscription.objects
            .select_related("business", "plan")
            .order_by("-started_at", "-created_at")
        )
        if q:
            subs = subs.filter(
                Q(business__name__icontains=q) |
                Q(plan__name__icontains=q) |
                Q(plan__code__icontains=q)
            )

        ctx.update(
            q=q,
            subs=list(subs),
            total=subs.count(),
            now=timezone.now(),
            active_tab="home",  # keeps base.html sidebar styles happy
        )
        return ctx


