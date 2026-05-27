# accounts/__init__.py
"""
Compatibility shim for accounts module imports.

The actual accounts app is located at circuitcity.accounts.
This package re-exports it to support imports like:
    import accounts
    from accounts.models import Profile
"""

# Import the real accounts module and re-export its attributes
import sys
from circuitcity import accounts as real_accounts

# Re-export all attributes from the real accounts module
for attr in dir(real_accounts):
    if not attr.startswith('_'):
        globals()[attr] = getattr(real_accounts, attr)

# Make submodules accessible (models, views, forms, etc.)
# This allows: from accounts.models import Profile

# Helper to safely register submodule aliases
def _register_submodule(alias, real_name):
    try:
        sys.modules[alias] = sys.modules[real_name]
    except KeyError:
        # Submodule doesn't exist or isn't loaded yet, that's okay
        pass

# Register common submodules
_register_submodule('accounts.models', 'circuitcity.accounts.models')
_register_submodule('accounts.forms', 'circuitcity.accounts.forms')
_register_submodule('accounts.views', 'circuitcity.accounts.views')
_register_submodule('accounts.admin', 'circuitcity.accounts.admin')
_register_submodule('accounts.urls', 'circuitcity.accounts.urls')
_register_submodule('accounts.middleware', 'circuitcity.accounts.middleware')
_register_submodule('accounts.context', 'circuitcity.accounts.context')
_register_submodule('accounts.utils', 'circuitcity.accounts.utils')
_register_submodule('accounts.services', 'circuitcity.accounts.services')
_register_submodule('accounts.decorators', 'circuitcity.accounts.decorators')
_register_submodule('accounts.validators', 'circuitcity.accounts.validators')
_register_submodule('accounts.emails', 'circuitcity.accounts.emails')

