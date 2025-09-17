# circuitcity/inventory/mixins.py
class BusinessQuerysetMixin:
    business_field = "business"
    def get_queryset(self):
        qs = super().get_queryset()
        biz = getattr(self.request, "business", None)
        return qs.filter(**{self.business_field: biz}) if biz else qs.none()
