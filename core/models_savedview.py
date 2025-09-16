from django.db import models
from django.contrib.auth import get_user_model
User = get_user_model()

class SavedView(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    scope = models.CharField(max_length=50)  # "stock_list", "agent_txns", etc.
    name  = models.CharField(max_length=80)
    query = models.JSONField(default=dict)   # {filters:{...}, sort:"-qty", columns:[...]}
    is_shared = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
