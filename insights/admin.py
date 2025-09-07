from django.contrib import admin
from . import models
admin.site.register([
    models.DailyKPI, models.ForecastRun, models.ForecastItem,
    models.InventoryPolicy, models.ReorderAdvice,
    models.Notification, models.Badge, models.AgentBadge,
    models.LeaderboardSnapshot, models.EmailReportLog
])
