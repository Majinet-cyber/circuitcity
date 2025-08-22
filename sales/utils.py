# sales/utils.py
from .models import Sale
from inventory.utils import user_in_group, AGENT

def sales_qs_for_user(user):
    qs = Sale.objects.all()
    if user_in_group(user, AGENT) and not user.is_superuser:
        # assuming Sale has a ForeignKey to User: sale.user or sale.agent
        agent_field = "user"  # change if your field is named differently
        qs = qs.filter(**{agent_field: user})
    return qs
