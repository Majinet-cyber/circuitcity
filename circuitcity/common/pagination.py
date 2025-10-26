# common/pagination.py
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from urllib.parse import urlencode

def paginate_qs(request, qs, default_per_page=50, max_per_page=200):
    try:
        per_page = int(request.GET.get("page_size", default_per_page))
    except (TypeError, ValueError):
        per_page = default_per_page
    per_page = min(max(per_page, 1), max_per_page)

    paginator = Paginator(qs, per_page)
    page_num = request.GET.get("page") or 1
    try:
        page_obj = paginator.page(page_num)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    def url_for(page):
        params = request.GET.copy()
        params["page"] = page
        return f"?{urlencode(params)}"

    return page_obj, url_for


