# inventory/liquor_catalog.py
"""
Single Source of Truth for Malawi Liquor Product Suggestions
Used by: Liquor Add Product Wizard, and other liquor-related features

This catalog provides common Malawi liquor products to reduce typing
and ensure consistency across the platform.
"""

# Comprehensive Malawi Liquor Product Catalog
# Organized by category with realistic local brands and products

LIQUOR_SUGGESTIONS = {
    'beer': [
        'Carlsberg',
        'Hunters Gold',
        'Castle Lite',
        'Chibuku Shake Shake',
        'Kuche Kuche',
        'Malawi Shandy',
        'Castel Beer',
        'Green',
        'Calsberg Export',
    ],
    
    'cider': [
        'Hunters Dry',
        'Hunters Gold Cider',
        'Savanna Dry',
        'Strongbow',
        'Smirnoff Spin',
        'Flying Fish',
    ],
    
    'wine': [
        '4th Street',
        'Tassenberg',
        'Grand Reserve',
        'Vino Rosso',
        'Drostdy-Hof',
        'Robertson',
        'KWV',
        'Nederburg',
    ],
    
    'spirits': [
        'Amarula',
        'Jägermeister',
        'Baileys Irish Cream',
        'Campari',
        'Cointreau',
        'Malibu',
        'Kahlúa',
        'Frangelico',
    ],
    
    'whiskey': [
        'Johnnie Walker Red Label',
        'Johnnie Walker Black Label',
        'Jameson',
        'Jack Daniels',
        'J&B',
        'Famous Grouse',
        'Bells',
        'Grant\'s',
        'Chivas Regal',
        'Glenfiddich',
    ],
    
    'gin': [
        'Gordons Gin',
        'Tanqueray',
        'Bombay Sapphire',
        'Beefeater',
        'Hendricks',
        'Gin & Tonic RTD',
        'Gordons Pink',
    ],
    
    'vodka': [
        'Smirnoff',
        'Absolut',
        'Flirt Vodka',
        'Russian Bear',
        'Skyy Vodka',
        'Ciroc',
        'Grey Goose',
        'Smirnoff Ice',
    ],
    
    'rum': [
        'Captain Morgan',
        'Bacardi',
        'Havana Club',
        'Malibu',
        'Stroh Rum',
        'Captain Morgan Spiced Gold',
        'Bacardi Superior',
    ],
    
    'brandy': [
        'Klipdrift',
        'Richelieu',
        'Viceroy',
        'Hennessy',
        'Rémy Martin',
        'Oude Meester',
        'Bisquit',
    ],
    
    'tequila': [
        'Jose Cuervo',
        'Olmeca',
        'Sauza',
        'Patrón',
        'Don Julio',
    ],
    
    'mixers': [
        'Coca-Cola',
        'Sprite',
        'Fanta Orange',
        'Tonic Water',
        'Soda Water',
        'Ginger Ale',
        'Bitter Lemon',
        'Schweppes Tonic',
        'Appletiser',
        'Grapetiser',
    ],
    
    'energy': [
        'Red Bull',
        'Monster Energy',
        'Power Horse',
        'Burn',
        'V Energy',
    ],
    
    'water': [
        'Bwanje Valley Water',
        'Mw Water',
        'Crystal Clear',
        'Dasani',
        'Aquafina',
        'Sparkling Water',
    ],
    
    'other': [
        # Fallback for uncategorized items
        'Other Product',
    ]
}


def get_suggestions_for_category(category: str) -> list:
    """
    Get product suggestions for a specific category.
    
    Args:
        category: Category name (e.g., 'beer', 'cider', 'wine')
        
    Returns:
        List of product name strings for that category
    """
    category = str(category).lower().strip()
    return LIQUOR_SUGGESTIONS.get(category, [])


def get_all_categories() -> list:
    """
    Get all available liquor categories.
    
    Returns:
        List of category names
    """
    return list(LIQUOR_SUGGESTIONS.keys())


def get_all_suggestions() -> dict:
    """
    Get the complete liquor suggestions dictionary.
    
    Returns:
        Dictionary mapping categories to product lists
    """
    return LIQUOR_SUGGESTIONS.copy()


# Category display metadata (icons, labels, descriptions)
CATEGORY_METADATA = {
    'beer': {
        'label': 'Beer',
        'icon': '🍺',
        'description': 'Beers and lagers'
    },
    'cider': {
        'label': 'Cider',
        'icon': '🍎',
        'description': 'Ciders and flavored drinks'
    },
    'wine': {
        'label': 'Wine',
        'icon': '🍷',
        'description': 'Red, white, and rosé wines'
    },
    'spirits': {
        'label': 'Spirits',
        'icon': '🥃',
        'description': 'Liqueurs and specialty spirits'
    },
    'whiskey': {
        'label': 'Whiskey',
        'icon': '🥃',
        'description': 'Whiskey and bourbon'
    },
    'gin': {
        'label': 'Gin',
        'icon': '🍸',
        'description': 'Gin and gin-based drinks'
    },
    'vodka': {
        'label': 'Vodka',
        'icon': '🧊',
        'description': 'Vodka and vodka mixes'
    },
    'rum': {
        'label': 'Rum',
        'icon': '🏝️',
        'description': 'Light and dark rum'
    },
    'brandy': {
        'label': 'Brandy',
        'icon': '🍇',
        'description': 'Brandy and cognac'
    },
    'tequila': {
        'label': 'Tequila',
        'icon': '🌵',
        'description': 'Tequila and mezcal'
    },
    'mixers': {
        'label': 'Mixers',
        'icon': '🧃',
        'description': 'Soft drinks and mixers'
    },
    'energy': {
        'label': 'Energy Drinks',
        'icon': '⚡',
        'description': 'Energy and sports drinks'
    },
    'water': {
        'label': 'Water',
        'icon': '💧',
        'description': 'Still and sparkling water'
    },
    'other': {
        'label': 'Other',
        'icon': '📦',
        'description': 'Other beverages'
    }
}


def get_category_metadata(category: str) -> dict:
    """
    Get display metadata for a category.
    
    Args:
        category: Category name
        
    Returns:
        Dictionary with 'label', 'icon', and 'description' keys
    """
    category = str(category).lower().strip()
    return CATEGORY_METADATA.get(category, {
        'label': category.title(),
        'icon': '📦',
        'description': category.title()
    })


__all__ = [
    'LIQUOR_SUGGESTIONS',
    'get_suggestions_for_category',
    'get_all_categories',
    'get_all_suggestions',
    'CATEGORY_METADATA',
    'get_category_metadata',
]

