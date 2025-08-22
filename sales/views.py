from django.views.generic import ListView
from common.pagination import paginate_qs
from sales.models import Sale

class SaleListView(ListView):
    template_name = "sales/list.html"
    context_object_name = "page_obj"  # so templates match
    paginate_by = None  # we’ll handle it ourselves

    def get_queryset(self):
        return (Sale.objects
                .select_related("item","agent","location")
                .only("id","sold_at","price","commission_pct","item__imei","agent__username","location__name")
                .order_by("-created_at"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        page_obj, url_for = paginate_qs(self.request, self.get_queryset())
        ctx.update({"page_obj": page_obj, "url_for": url_for})
        return ctx
