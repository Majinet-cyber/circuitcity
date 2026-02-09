"""
Vertical Adapters for Corrections Framework
============================================

Each vertical implements an adapter that registers its correctable entities.

Auto-discovery:
- Import all adapter modules here to trigger @register_vertical decorators
"""

# Import all adapters to trigger registration
from corrections.adapters import phones  # noqa: F401
from corrections.adapters import clothing  # noqa: F401
from corrections.adapters import gym  # noqa: F401
from corrections.adapters import pharmacy  # noqa: F401

# TODO: Add more adapters as they're implemented
# from corrections.adapters import liquor  # noqa: F401
# from corrections.adapters import welding  # noqa: F401
# from corrections.adapters import farm  # noqa: F401

