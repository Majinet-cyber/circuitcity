from datetime import datetime, time
from zoneinfo import ZoneInfo


CAT_ZONE = ZoneInfo("Africa/Blantyre")
WEEKDAY_OPEN = time(9, 0)
WEEKDAY_CLOSE = time(18, 0)
SATURDAY_CLOSE = time(17, 0)


def current_cat_time():
    return datetime.now(CAT_ZONE)


def is_business_hours(now=None):
    now = now or current_cat_time()
    if now.tzinfo is None:
        now = now.replace(tzinfo=CAT_ZONE)
    now = now.astimezone(CAT_ZONE)

    if now.weekday() == 6:
        return False
    if now.weekday() == 5:
        return WEEKDAY_OPEN <= now.time() < SATURDAY_CLOSE
    return WEEKDAY_OPEN <= now.time() < WEEKDAY_CLOSE


def business_hours_context(now=None):
    now = now or current_cat_time()
    return {
        "is_business_hours": is_business_hours(now),
        "business_hours_now": now.astimezone(CAT_ZONE),
        "business_hours_label": "Monday-Friday: 9am-6pm CAT; Saturday: 9am-5pm CAT; Sunday: closed",
    }
