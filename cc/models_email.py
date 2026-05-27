# cc/models_email.py
"""
SSOT Email Delivery Log Model - Compatibility Alias
The EmailDeliveryLog model is now in the notifications app.
This file provides backward compatibility for existing imports.
"""

# Re-export from notifications app for backward compatibility
from notifications.models import EmailDeliveryLog

__all__ = ['EmailDeliveryLog']
