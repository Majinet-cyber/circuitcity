"""
Corrections App Configuration (Feb 2026)
=========================================

Ensures vertical adapters are auto-loaded at Django startup.
"""
from django.apps import AppConfig


class CorrectionsConfig(AppConfig):
    """App configuration for corrections framework."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'corrections'
    verbose_name = 'Data Corrections'
    
    def ready(self):
        """
        Called when Django starts.
        
        Import all vertical adapters to trigger @register_vertical decorators.
        """
        # Import adapters to register them with the registry
        try:
            from corrections.adapters import phones  # noqa: F401
            from corrections.adapters import gym  # noqa: F401
            from corrections.adapters import clothing  # noqa: F401
            print('[Corrections] Adapters loaded: phones, gym, clothing')
        except ImportError as e:
            print(f'[Corrections] Warning: Failed to load some adapters: {e}')

