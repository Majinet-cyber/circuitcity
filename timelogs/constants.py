# timelogs/constants.py
"""
Constants for timelog work hours, bonuses, and penalties.
SINGLE SOURCE OF TRUTH for time-based calculations.
"""
from datetime import time
from decimal import Decimal

# Work hours (local time)
WORK_START = time(8, 0)  # 08:00
WORK_END = time(17, 30)  # 17:30

# Bonus and penalty amounts (MWK)
EARLY_BONUS_PER_30 = Decimal("5000.00")  # +5,000 per 30 minutes early
LATE_PENALTY_PER_30 = Decimal("7000.00")  # -7,000 per 30 minutes late

# Geofence radius (meters) - default if location doesn't specify
DEFAULT_GEOFENCE_RADIUS_M = 150

