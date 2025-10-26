# inventory/views_dispatch.py (new file)  â€” or put in views.py if you prefer
from django.shortcuts import redirect
from .helpers import product_new_url_for_business
from tenants.decorators import require_business  # you already use this
from django.contrib.auth.decorators import login_required

@login_required
@require_business
def product_new_entry(request):
    """
    Redirect 'Add Product' to the correct, business-specific form.
    Legacy businesses go to PHONE/Electronics by default.
    """
    return redirect(product_new_url_for_business(request.business))


