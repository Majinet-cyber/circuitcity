# tenants/views_mixins.py
class TenantCreateMixin:
    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.business = self.request.business
        obj.save()
        return super().form_valid(form)

# For function views:
def save_with_business(obj, request):
    obj.business = request.business
    obj.save()
    return obj
