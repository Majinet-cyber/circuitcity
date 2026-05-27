# inventory/mixed_retail_seed.py
"""
Mixed Retail seed data — departments, categories, and product templates.

Usage:
    from inventory.mixed_retail_seed import seed_mixed_retail_catalog
    seed_mixed_retail_catalog()

All functions are idempotent — safe to run multiple times.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Department + category catalog (20 departments)
# ---------------------------------------------------------------------------

SEED_CATALOG = [
    {
        "name": "Phones & Electronics",
        "slug": "electronics",
        "icon": "bi-phone",
        "description": "Smartphones, laptops, TVs, cables, accessories and all electronics",
        "sort_order": 10,
        "categories": [
            {"name": "Smartphones", "slug": "smartphones", "sort_order": 10},
            {"name": "Feature Phones", "slug": "feature-phones", "sort_order": 20},
            {"name": "Laptops", "slug": "laptops", "sort_order": 30},
            {"name": "Tablets", "slug": "tablets", "sort_order": 40},
            {"name": "TVs", "slug": "tvs", "sort_order": 50},
            {"name": "Speakers", "slug": "speakers", "sort_order": 60},
            {"name": "Radios", "slug": "radios", "sort_order": 70},
            {"name": "Earphones", "slug": "earphones", "sort_order": 80},
            {"name": "Headphones", "slug": "headphones", "sort_order": 90},
            {"name": "Chargers", "slug": "chargers", "sort_order": 100},
            {"name": "Power Banks", "slug": "power-banks", "sort_order": 110},
            {"name": "Cables", "slug": "cables", "sort_order": 120},
            {"name": "Memory Cards", "slug": "memory-cards", "sort_order": 130},
            {"name": "Flash Drives", "slug": "flash-drives", "sort_order": 140},
            {"name": "Phone Cases", "slug": "phone-cases", "sort_order": 150},
            {"name": "Screen Protectors", "slug": "screen-protectors", "sort_order": 160},
            {"name": "Smart Watches", "slug": "smart-watches", "sort_order": 170},
            {"name": "Routers", "slug": "routers", "sort_order": 180},
            {"name": "Batteries", "slug": "batteries", "sort_order": 190},
            {"name": "Electronic Accessories", "slug": "electronic-accessories", "sort_order": 200},
        ],
    },
    {
        "name": "Clothing & Fashion",
        "slug": "clothing-fashion",
        "icon": "bi-bag-heart",
        "description": "Shirts, trousers, dresses, suits, jackets and all apparel",
        "sort_order": 20,
        "categories": [
            {"name": "Shirts", "slug": "shirts", "sort_order": 10},
            {"name": "T-Shirts", "slug": "t-shirts", "sort_order": 20},
            {"name": "Dresses", "slug": "dresses", "sort_order": 30},
            {"name": "Trousers", "slug": "trousers", "sort_order": 40},
            {"name": "Jeans", "slug": "jeans", "sort_order": 50},
            {"name": "Suits", "slug": "suits", "sort_order": 60},
            {"name": "Jackets", "slug": "jackets", "sort_order": 70},
            {"name": "Skirts", "slug": "skirts", "sort_order": 80},
            {"name": "Caps & Hats", "slug": "caps", "sort_order": 90},
            {"name": "Belts", "slug": "belts", "sort_order": 100},
            {"name": "Children's Wear", "slug": "childrens-wear", "sort_order": 110},
            {"name": "School Uniforms", "slug": "school-uniforms", "sort_order": 120},
            {"name": "Underwear", "slug": "underwear", "sort_order": 130},
            {"name": "Fabrics", "slug": "fabrics", "sort_order": 140},
            {"name": "Traditional Wear", "slug": "traditional-wear", "sort_order": 150},
            {"name": "Sweaters & Hoodies", "slug": "sweaters", "sort_order": 160},
            {"name": "Sportswear", "slug": "sportswear", "sort_order": 170},
        ],
    },
    {
        "name": "Shoes",
        "slug": "shoes",
        "icon": "bi-boot",
        "description": "Sneakers, formal shoes, sandals, boots, heels and all footwear",
        "sort_order": 30,
        "categories": [
            {"name": "Sneakers", "slug": "sneakers", "sort_order": 10},
            {"name": "Formal Shoes", "slug": "formal-shoes", "sort_order": 20},
            {"name": "Sandals", "slug": "sandals", "sort_order": 30},
            {"name": "Slippers", "slug": "slippers", "sort_order": 40},
            {"name": "Boots", "slug": "boots", "sort_order": 50},
            {"name": "School Shoes", "slug": "school-shoes", "sort_order": 60},
            {"name": "Ladies Heels", "slug": "ladies-heels", "sort_order": 70},
            {"name": "Kids Shoes", "slug": "kids-shoes", "sort_order": 80},
            {"name": "Sports Shoes", "slug": "sports-shoes", "sort_order": 90},
        ],
    },
    {
        "name": "Grocery & General",
        "slug": "general-goods",
        "icon": "bi-box-seam",
        "description": "Sugar, rice, cooking oil, soap, household essentials and general goods",
        "sort_order": 40,
        "categories": [
            {"name": "Groceries", "slug": "groceries", "sort_order": 10},
            {"name": "Grains & Flour", "slug": "grains-flour", "sort_order": 20},
            {"name": "Cooking Oils", "slug": "cooking-oils", "sort_order": 30},
            {"name": "Beverages", "slug": "beverages", "sort_order": 40},
            {"name": "Household Items", "slug": "household-items", "sort_order": 50},
            {"name": "Cleaning Products", "slug": "cleaning-products", "sort_order": 60},
            {"name": "Stationery", "slug": "stationery", "sort_order": 70},
            {"name": "Toys", "slug": "toys", "sort_order": 80},
            {"name": "Plasticware", "slug": "plasticware", "sort_order": 90},
            {"name": "Accessories", "slug": "accessories", "sort_order": 100},
        ],
    },
    {
        "name": "Furniture",
        "slug": "furniture",
        "icon": "bi-lamp",
        "description": "Chairs, tables, beds, sofas, wardrobes and all furniture",
        "sort_order": 50,
        "categories": [
            {"name": "Tables", "slug": "tables", "sort_order": 10},
            {"name": "Chairs", "slug": "chairs", "sort_order": 20},
            {"name": "Beds", "slug": "beds", "sort_order": 30},
            {"name": "Sofas", "slug": "sofas", "sort_order": 40},
            {"name": "Wardrobes", "slug": "wardrobes", "sort_order": 50},
            {"name": "TV Stands", "slug": "tv-stands", "sort_order": 60},
            {"name": "Desks", "slug": "desks", "sort_order": 70},
            {"name": "Shelves", "slug": "shelves", "sort_order": 80},
            {"name": "Cupboards", "slug": "cupboards", "sort_order": 90},
            {"name": "Mattresses", "slug": "mattresses", "sort_order": 100},
            {"name": "Dining Sets", "slug": "dining-sets", "sort_order": 110},
            {"name": "Office Chairs", "slug": "office-chairs", "sort_order": 120},
        ],
    },
    {
        "name": "Home Appliances",
        "slug": "home-appliances",
        "icon": "bi-house-gear",
        "description": "Kettles, microwaves, fridges, irons, fans and household appliances",
        "sort_order": 60,
        "categories": [
            {"name": "Kettles", "slug": "kettles", "sort_order": 10},
            {"name": "Microwaves", "slug": "microwaves", "sort_order": 20},
            {"name": "Blenders", "slug": "blenders", "sort_order": 30},
            {"name": "Irons", "slug": "irons", "sort_order": 40},
            {"name": "Fans", "slug": "fans", "sort_order": 50},
            {"name": "Rice Cookers", "slug": "rice-cookers", "sort_order": 60},
            {"name": "Fridges", "slug": "fridges", "sort_order": 70},
            {"name": "Freezers", "slug": "freezers", "sort_order": 80},
            {"name": "Gas Cookers", "slug": "gas-cookers", "sort_order": 90},
            {"name": "Electric Cookers", "slug": "electric-cookers", "sort_order": 100},
            {"name": "Extension Leads", "slug": "extension-leads", "sort_order": 110},
            {"name": "Washing Machines", "slug": "washing-machines", "sort_order": 120},
        ],
    },
    {
        "name": "Hardware & Tools",
        "slug": "hardware-tools",
        "icon": "bi-tools",
        "description": "Hammers, drills, nails, padlocks, wires, pipes and hardware items",
        "sort_order": 70,
        "categories": [
            {"name": "Hand Tools", "slug": "hand-tools", "sort_order": 10},
            {"name": "Nails & Screws", "slug": "nails-screws", "sort_order": 20},
            {"name": "Locks & Security", "slug": "locks-security", "sort_order": 30},
            {"name": "Wires & Cables", "slug": "wires-cables", "sort_order": 40},
            {"name": "Pipes & Fittings", "slug": "pipes-fittings", "sort_order": 50},
            {"name": "Paint & Brushes", "slug": "paint-brushes", "sort_order": 60},
            {"name": "Measuring Tools", "slug": "measuring-tools", "sort_order": 70},
            {"name": "Hardware Basics", "slug": "hardware-basics", "sort_order": 80},
            {"name": "Small Tools", "slug": "small-tools", "sort_order": 90},
        ],
    },
    {
        "name": "Building Materials",
        "slug": "building-materials",
        "icon": "bi-bricks",
        "description": "Cement, bricks, roofing, tiles, timber, paint and construction materials",
        "sort_order": 80,
        "categories": [
            {"name": "Cement & Mortar", "slug": "cement-mortar", "sort_order": 10},
            {"name": "Bricks & Blocks", "slug": "bricks-blocks", "sort_order": 20},
            {"name": "Roofing", "slug": "roofing", "sort_order": 30},
            {"name": "Timber & Wood", "slug": "timber-wood", "sort_order": 40},
            {"name": "Tiles & Adhesive", "slug": "tiles-adhesive", "sort_order": 50},
            {"name": "Paint", "slug": "paint", "sort_order": 60},
            {"name": "Sand & Aggregate", "slug": "sand-aggregate", "sort_order": 70},
            {"name": "Steel & Reinforcing", "slug": "steel-reinforcing", "sort_order": 80},
        ],
    },
    {
        "name": "Cosmetics & Beauty",
        "slug": "beauty-cosmetics",
        "icon": "bi-stars",
        "description": "Lotions, perfumes, hair products, makeup, skin care and beauty supplies",
        "sort_order": 90,
        "categories": [
            {"name": "Lotions", "slug": "lotions", "sort_order": 10},
            {"name": "Perfumes", "slug": "perfumes", "sort_order": 20},
            {"name": "Hair Products", "slug": "hair-products", "sort_order": 30},
            {"name": "Makeup", "slug": "makeup", "sort_order": 40},
            {"name": "Body Sprays", "slug": "body-sprays", "sort_order": 50},
            {"name": "Skin Care", "slug": "skin-care", "sort_order": 60},
            {"name": "Wigs & Extensions", "slug": "wigs", "sort_order": 70},
            {"name": "Nail Products", "slug": "nail-products", "sort_order": 80},
            {"name": "Barber Products", "slug": "barber-products", "sort_order": 90},
        ],
    },
    {
        "name": "Pharmacy & Personal Care",
        "slug": "pharmacy-personal-care",
        "icon": "bi-capsule",
        "description": "Medicines, bandages, vitamins, diapers, sanitary and personal care items",
        "sort_order": 100,
        "categories": [
            {"name": "Pain Relief", "slug": "pain-relief", "sort_order": 10},
            {"name": "Vitamins & Supplements", "slug": "vitamins-supplements", "sort_order": 20},
            {"name": "First Aid", "slug": "first-aid", "sort_order": 30},
            {"name": "Cough & Cold", "slug": "cough-cold", "sort_order": 40},
            {"name": "Sanitary Products", "slug": "sanitary-products", "sort_order": 50},
            {"name": "Baby & Infant Care", "slug": "baby-infant-care", "sort_order": 60},
            {"name": "Protective Equipment", "slug": "protective-equipment", "sort_order": 70},
        ],
    },
    {
        "name": "Bags & Accessories",
        "slug": "bags-accessories",
        "icon": "bi-handbag",
        "description": "Handbags, backpacks, wallets, watches, sunglasses and accessories",
        "sort_order": 110,
        "categories": [
            {"name": "Handbags", "slug": "handbags", "sort_order": 10},
            {"name": "Backpacks", "slug": "backpacks", "sort_order": 20},
            {"name": "Wallets", "slug": "wallets", "sort_order": 30},
            {"name": "School Bags", "slug": "school-bags", "sort_order": 40},
            {"name": "Travel Bags", "slug": "travel-bags", "sort_order": 50},
            {"name": "Watches", "slug": "watches", "sort_order": 60},
            {"name": "Sunglasses", "slug": "sunglasses", "sort_order": 70},
            {"name": "Jewellery", "slug": "jewellery", "sort_order": 80},
        ],
    },
    {
        "name": "Office & Stationery",
        "slug": "office-stationery",
        "icon": "bi-pencil-square",
        "description": "Exercise books, pens, printer paper, files, calculators and office supplies",
        "sort_order": 120,
        "categories": [
            {"name": "Books & Notebooks", "slug": "books-notebooks", "sort_order": 10},
            {"name": "Pens & Pencils", "slug": "pens-pencils", "sort_order": 20},
            {"name": "Paper Products", "slug": "paper-products", "sort_order": 30},
            {"name": "Filing & Storage", "slug": "filing-storage", "sort_order": 40},
            {"name": "Calculators & Devices", "slug": "calculators-devices", "sort_order": 50},
            {"name": "Staplers & Clips", "slug": "staplers-clips", "sort_order": 60},
        ],
    },
    {
        "name": "Kitchenware",
        "slug": "kitchenware",
        "icon": "bi-cup-hot",
        "description": "Plates, pots, pans, cups, cutlery, basins and kitchen items",
        "sort_order": 130,
        "categories": [
            {"name": "Plates & Bowls", "slug": "plates-bowls", "sort_order": 10},
            {"name": "Cups & Mugs", "slug": "cups-mugs", "sort_order": 20},
            {"name": "Cooking Pots", "slug": "cooking-pots", "sort_order": 30},
            {"name": "Frying Pans", "slug": "frying-pans", "sort_order": 40},
            {"name": "Cutlery", "slug": "cutlery", "sort_order": 50},
            {"name": "Food Containers", "slug": "food-containers", "sort_order": 60},
            {"name": "Basins & Buckets", "slug": "basins-buckets", "sort_order": 70},
            {"name": "Flasks & Thermos", "slug": "flasks-thermos", "sort_order": 80},
        ],
    },
    {
        "name": "Auto Accessories",
        "slug": "auto-accessories",
        "icon": "bi-car-front",
        "description": "Car batteries, engine oil, seat covers, wipers, bulbs and vehicle accessories",
        "sort_order": 140,
        "categories": [
            {"name": "Car Batteries", "slug": "car-batteries", "sort_order": 10},
            {"name": "Engine & Fluids", "slug": "engine-fluids", "sort_order": 20},
            {"name": "Interior Accessories", "slug": "interior-accessories", "sort_order": 30},
            {"name": "Lights & Bulbs", "slug": "lights-bulbs", "sort_order": 40},
            {"name": "Car Electronics", "slug": "car-electronics", "sort_order": 50},
            {"name": "Tyres & Maintenance", "slug": "tyres-maintenance", "sort_order": 60},
        ],
    },
    {
        "name": "Services",
        "slug": "services-non-stock",
        "icon": "bi-wrench-adjustable",
        "description": "Repairs, installations, delivery, consultations and non-stock income",
        "sort_order": 150,
        "categories": [
            {"name": "Repairs", "slug": "repairs", "sort_order": 10},
            {"name": "Delivery", "slug": "delivery", "sort_order": 20},
            {"name": "Installation", "slug": "installation", "sort_order": 30},
            {"name": "Consultation", "slug": "consultation", "sort_order": 40},
            {"name": "Labour", "slug": "labour", "sort_order": 50},
            {"name": "Custom Service", "slug": "custom-service", "sort_order": 60},
            {"name": "Other Non-stock Income", "slug": "other-non-stock", "sort_order": 70},
        ],
    },
    {
        "name": "Baby & Kids",
        "slug": "baby-kids",
        "icon": "bi-balloon-heart",
        "description": "Baby clothes, diapers, feeding bottles, toys, school bags and kids items",
        "sort_order": 160,
        "categories": [
            {"name": "Baby Clothing", "slug": "baby-clothing", "sort_order": 10},
            {"name": "Diapers & Nappies", "slug": "diapers-nappies", "sort_order": 20},
            {"name": "Baby Care", "slug": "baby-care", "sort_order": 30},
            {"name": "Feeding", "slug": "baby-feeding", "sort_order": 40},
            {"name": "Toys & Games", "slug": "toys-games", "sort_order": 50},
            {"name": "Kids School Items", "slug": "kids-school-items", "sort_order": 60},
        ],
    },
    {
        "name": "Agriculture Inputs",
        "slug": "agriculture-inputs",
        "icon": "bi-flower2",
        "description": "Fertilizers, seeds, pesticides, sprayers, hoes and farming supplies",
        "sort_order": 170,
        "categories": [
            {"name": "Fertilizers", "slug": "fertilizers", "sort_order": 10},
            {"name": "Seeds", "slug": "seeds", "sort_order": 20},
            {"name": "Pesticides & Herbicides", "slug": "pesticides-herbicides", "sort_order": 30},
            {"name": "Farm Tools", "slug": "farm-tools", "sort_order": 40},
            {"name": "Animal Feed", "slug": "animal-feed", "sort_order": 50},
            {"name": "Irrigation", "slug": "irrigation", "sort_order": 60},
        ],
    },
    {
        "name": "Sports & Fitness",
        "slug": "sports-fitness",
        "icon": "bi-trophy",
        "description": "Gym equipment, sports gear, jerseys, shoes, water bottles and fitness items",
        "sort_order": 180,
        "categories": [
            {"name": "Gym Equipment", "slug": "gym-equipment", "sort_order": 10},
            {"name": "Sports Balls", "slug": "sports-balls", "sort_order": 20},
            {"name": "Jerseys & Sportswear", "slug": "jerseys-sportswear", "sort_order": 30},
            {"name": "Sports Shoes", "slug": "sports-shoes-dept", "sort_order": 40},
            {"name": "Fitness Accessories", "slug": "fitness-accessories", "sort_order": 50},
        ],
    },
    {
        "name": "Mobile Money & Agent Services",
        "slug": "mobile-money-services",
        "icon": "bi-cash-coin",
        "description": "Cash in, cash out, airtime, sim cards, agent float and mobile money services",
        "sort_order": 190,
        "categories": [
            {"name": "Cash In / Cash Out", "slug": "cash-in-out", "sort_order": 10},
            {"name": "Airtime & Data", "slug": "airtime-data", "sort_order": 20},
            {"name": "Sim Cards", "slug": "sim-cards", "sort_order": 30},
            {"name": "Agent Services", "slug": "agent-services", "sort_order": 40},
        ],
    },
    {
        "name": "Other / Custom",
        "slug": "other-custom",
        "icon": "bi-three-dots",
        "description": "Anything that does not fit the other departments — add your own items here",
        "sort_order": 200,
        "categories": [
            {"name": "Custom Items", "slug": "custom-items", "sort_order": 10},
            {"name": "Miscellaneous", "slug": "miscellaneous", "sort_order": 20},
        ],
    },
]


# ---------------------------------------------------------------------------
# Product template catalog — quick-start suggestions per department
# ---------------------------------------------------------------------------

PRODUCT_TEMPLATE_CATALOG: dict[str, list[dict]] = {
    "electronics": [
        {"name": "Smartphone", "unit": "pcs", "sort_order": 10},
        {"name": "Feature Phone", "unit": "pcs", "sort_order": 20},
        {"name": "Charger", "unit": "pcs", "sort_order": 30},
        {"name": "USB Cable", "unit": "pcs", "sort_order": 40},
        {"name": "Type-C Cable", "unit": "pcs", "sort_order": 50},
        {"name": "Earphones", "unit": "pcs", "sort_order": 60},
        {"name": "Bluetooth Headset", "unit": "pcs", "sort_order": 70},
        {"name": "Power Bank", "unit": "pcs", "sort_order": 80},
        {"name": "Screen Protector", "unit": "pcs", "sort_order": 90},
        {"name": "Phone Case", "unit": "pcs", "sort_order": 100},
        {"name": "Memory Card", "unit": "pcs", "sort_order": 110},
        {"name": "Laptop", "unit": "pcs", "sort_order": 120},
        {"name": "Laptop Charger", "unit": "pcs", "sort_order": 130},
        {"name": "TV", "unit": "pcs", "sort_order": 140},
        {"name": "Speaker", "unit": "pcs", "sort_order": 150},
        {"name": "Radio", "unit": "pcs", "sort_order": 160},
        {"name": "Smartwatch", "unit": "pcs", "sort_order": 170},
        {"name": "Router", "unit": "pcs", "sort_order": 180},
        {"name": "Flash Drive", "unit": "pcs", "sort_order": 190},
        {"name": "Tablet", "unit": "pcs", "sort_order": 200},
    ],
    "clothing-fashion": [
        {"name": "T-Shirt", "unit": "pcs", "sort_order": 10},
        {"name": "Shirt", "unit": "pcs", "sort_order": 20},
        {"name": "Trousers", "unit": "pcs", "sort_order": 30},
        {"name": "Jeans", "unit": "pcs", "sort_order": 40},
        {"name": "Dress", "unit": "pcs", "sort_order": 50},
        {"name": "Skirt", "unit": "pcs", "sort_order": 60},
        {"name": "Suit", "unit": "pcs", "sort_order": 70},
        {"name": "Jacket", "unit": "pcs", "sort_order": 80},
        {"name": "Hoodie", "unit": "pcs", "sort_order": 90},
        {"name": "School Uniform", "unit": "pcs", "sort_order": 100},
        {"name": "Cap", "unit": "pcs", "sort_order": 110},
        {"name": "Belt", "unit": "pcs", "sort_order": 120},
        {"name": "Fabric (per metre)", "unit": "m", "sort_order": 130},
        {"name": "Chitenje Fabric", "unit": "pcs", "sort_order": 140},
        {"name": "Underwear", "unit": "pcs", "sort_order": 150},
    ],
    "shoes": [
        {"name": "Sneakers", "unit": "pair", "sort_order": 10},
        {"name": "Formal Shoes", "unit": "pair", "sort_order": 20},
        {"name": "Sandals", "unit": "pair", "sort_order": 30},
        {"name": "Slippers", "unit": "pair", "sort_order": 40},
        {"name": "Boots", "unit": "pair", "sort_order": 50},
        {"name": "School Shoes", "unit": "pair", "sort_order": 60},
        {"name": "Ladies Heels", "unit": "pair", "sort_order": 70},
        {"name": "Kids Shoes", "unit": "pair", "sort_order": 80},
        {"name": "Sports Shoes", "unit": "pair", "sort_order": 90},
    ],
    "general-goods": [
        {"name": "Sugar (kg)", "unit": "kg", "sort_order": 10},
        {"name": "Rice (kg)", "unit": "kg", "sort_order": 20},
        {"name": "Cooking Oil (litre)", "unit": "litre", "sort_order": 30},
        {"name": "Salt (pack)", "unit": "pack", "sort_order": 40},
        {"name": "Maize Flour (kg)", "unit": "kg", "sort_order": 50},
        {"name": "Bread", "unit": "pcs", "sort_order": 60},
        {"name": "Milk (litre)", "unit": "litre", "sort_order": 70},
        {"name": "Tea (pack)", "unit": "pack", "sort_order": 80},
        {"name": "Soap", "unit": "pcs", "sort_order": 90},
        {"name": "Toothpaste", "unit": "pcs", "sort_order": 100},
        {"name": "Matches", "unit": "pcs", "sort_order": 110},
        {"name": "Candles", "unit": "pack", "sort_order": 120},
        {"name": "Biscuits", "unit": "pack", "sort_order": 130},
        {"name": "Soft Drinks", "unit": "pcs", "sort_order": 140},
        {"name": "Bottled Water", "unit": "pcs", "sort_order": 150},
        {"name": "Washing Powder", "unit": "pack", "sort_order": 160},
    ],
    "furniture": [
        {"name": "Chair", "unit": "pcs", "sort_order": 10},
        {"name": "Table", "unit": "pcs", "sort_order": 20},
        {"name": "Bed", "unit": "pcs", "sort_order": 30},
        {"name": "Sofa", "unit": "pcs", "sort_order": 40},
        {"name": "Wardrobe", "unit": "pcs", "sort_order": 50},
        {"name": "TV Stand", "unit": "pcs", "sort_order": 60},
        {"name": "Desk", "unit": "pcs", "sort_order": 70},
        {"name": "Bookshelf", "unit": "pcs", "sort_order": 80},
        {"name": "Mattress", "unit": "pcs", "sort_order": 90},
        {"name": "Dining Set", "unit": "set", "sort_order": 100},
        {"name": "Cupboard", "unit": "pcs", "sort_order": 110},
    ],
    "home-appliances": [
        {"name": "Electric Kettle", "unit": "pcs", "sort_order": 10},
        {"name": "Iron", "unit": "pcs", "sort_order": 20},
        {"name": "Microwave", "unit": "pcs", "sort_order": 30},
        {"name": "Blender", "unit": "pcs", "sort_order": 40},
        {"name": "Rice Cooker", "unit": "pcs", "sort_order": 50},
        {"name": "Fan", "unit": "pcs", "sort_order": 60},
        {"name": "Fridge", "unit": "pcs", "sort_order": 70},
        {"name": "Freezer", "unit": "pcs", "sort_order": 80},
        {"name": "Gas Stove", "unit": "pcs", "sort_order": 90},
        {"name": "Extension Cable", "unit": "pcs", "sort_order": 100},
        {"name": "Washing Machine", "unit": "pcs", "sort_order": 110},
    ],
    "hardware-tools": [
        {"name": "Hammer", "unit": "pcs", "sort_order": 10},
        {"name": "Screwdriver", "unit": "pcs", "sort_order": 20},
        {"name": "Drill", "unit": "pcs", "sort_order": 30},
        {"name": "Nails (pack)", "unit": "pack", "sort_order": 40},
        {"name": "Screws (pack)", "unit": "pack", "sort_order": 50},
        {"name": "Hinges (pair)", "unit": "pair", "sort_order": 60},
        {"name": "Door Lock", "unit": "pcs", "sort_order": 70},
        {"name": "Padlock", "unit": "pcs", "sort_order": 80},
        {"name": "Paint Brush", "unit": "pcs", "sort_order": 90},
        {"name": "Measuring Tape", "unit": "pcs", "sort_order": 100},
        {"name": "Pliers", "unit": "pcs", "sort_order": 110},
        {"name": "Electrical Wire (m)", "unit": "m", "sort_order": 120},
        {"name": "PVC Pipe", "unit": "pcs", "sort_order": 130},
    ],
    "building-materials": [
        {"name": "Cement (bag)", "unit": "pcs", "sort_order": 10},
        {"name": "Bricks", "unit": "pcs", "sort_order": 20},
        {"name": "Roofing Sheets", "unit": "pcs", "sort_order": 30},
        {"name": "Timber (metre)", "unit": "m", "sort_order": 40},
        {"name": "Paint (tin)", "unit": "pcs", "sort_order": 50},
        {"name": "Tile Adhesive", "unit": "pcs", "sort_order": 60},
        {"name": "Floor Tiles", "unit": "pcs", "sort_order": 70},
        {"name": "Sand (load)", "unit": "other", "sort_order": 80},
        {"name": "Quarry Stone", "unit": "pcs", "sort_order": 90},
        {"name": "Steel Bars", "unit": "pcs", "sort_order": 100},
    ],
    "beauty-cosmetics": [
        {"name": "Lotion", "unit": "pcs", "sort_order": 10},
        {"name": "Perfume", "unit": "pcs", "sort_order": 20},
        {"name": "Hair Oil", "unit": "pcs", "sort_order": 30},
        {"name": "Hair Extensions", "unit": "pcs", "sort_order": 40},
        {"name": "Makeup Kit", "unit": "pcs", "sort_order": 50},
        {"name": "Nail Polish", "unit": "pcs", "sort_order": 60},
        {"name": "Face Cream", "unit": "pcs", "sort_order": 70},
        {"name": "Body Spray", "unit": "pcs", "sort_order": 80},
        {"name": "Shampoo", "unit": "pcs", "sort_order": 90},
        {"name": "Conditioner", "unit": "pcs", "sort_order": 100},
        {"name": "Wig", "unit": "pcs", "sort_order": 110},
    ],
    "pharmacy-personal-care": [
        {"name": "Pain Relief Tablets", "unit": "pack", "sort_order": 10},
        {"name": "Bandages", "unit": "pack", "sort_order": 20},
        {"name": "Antiseptic", "unit": "pcs", "sort_order": 30},
        {"name": "Vitamins", "unit": "pack", "sort_order": 40},
        {"name": "Sanitary Pads", "unit": "pack", "sort_order": 50},
        {"name": "Baby Diapers (pack)", "unit": "pack", "sort_order": 60},
        {"name": "Cough Syrup", "unit": "pcs", "sort_order": 70},
        {"name": "Thermometer", "unit": "pcs", "sort_order": 80},
        {"name": "Gloves (box)", "unit": "box", "sort_order": 90},
        {"name": "Face Masks (box)", "unit": "box", "sort_order": 100},
    ],
    "bags-accessories": [
        {"name": "Handbag", "unit": "pcs", "sort_order": 10},
        {"name": "Backpack", "unit": "pcs", "sort_order": 20},
        {"name": "Wallet", "unit": "pcs", "sort_order": 30},
        {"name": "School Bag", "unit": "pcs", "sort_order": 40},
        {"name": "Travel Bag", "unit": "pcs", "sort_order": 50},
        {"name": "Watch", "unit": "pcs", "sort_order": 60},
        {"name": "Sunglasses", "unit": "pcs", "sort_order": 70},
        {"name": "Bracelet", "unit": "pcs", "sort_order": 80},
        {"name": "Necklace", "unit": "pcs", "sort_order": 90},
    ],
    "office-stationery": [
        {"name": "Exercise Book", "unit": "pcs", "sort_order": 10},
        {"name": "Pen", "unit": "pcs", "sort_order": 20},
        {"name": "Pencil", "unit": "pcs", "sort_order": 30},
        {"name": "Marker", "unit": "pcs", "sort_order": 40},
        {"name": "Printer Paper (ream)", "unit": "pack", "sort_order": 50},
        {"name": "Stapler", "unit": "pcs", "sort_order": 60},
        {"name": "File Folder", "unit": "pcs", "sort_order": 70},
        {"name": "Calculator", "unit": "pcs", "sort_order": 80},
        {"name": "Envelope (pack)", "unit": "pack", "sort_order": 90},
        {"name": "Receipt Book", "unit": "pcs", "sort_order": 100},
    ],
    "kitchenware": [
        {"name": "Plate", "unit": "pcs", "sort_order": 10},
        {"name": "Cup", "unit": "pcs", "sort_order": 20},
        {"name": "Cooking Pot", "unit": "pcs", "sort_order": 30},
        {"name": "Frying Pan", "unit": "pcs", "sort_order": 40},
        {"name": "Spoon (set)", "unit": "set", "sort_order": 50},
        {"name": "Kitchen Knife", "unit": "pcs", "sort_order": 60},
        {"name": "Flask / Thermos", "unit": "pcs", "sort_order": 70},
        {"name": "Bucket", "unit": "pcs", "sort_order": 80},
        {"name": "Basin", "unit": "pcs", "sort_order": 90},
        {"name": "Food Container", "unit": "pcs", "sort_order": 100},
    ],
    "auto-accessories": [
        {"name": "Car Battery", "unit": "pcs", "sort_order": 10},
        {"name": "Engine Oil (litre)", "unit": "litre", "sort_order": 20},
        {"name": "Seat Covers (set)", "unit": "set", "sort_order": 30},
        {"name": "Car Mats (set)", "unit": "set", "sort_order": 40},
        {"name": "Wipers (pair)", "unit": "pair", "sort_order": 50},
        {"name": "Bulbs", "unit": "pcs", "sort_order": 60},
        {"name": "Tyre Pressure Gauge", "unit": "pcs", "sort_order": 70},
        {"name": "Phone Holder", "unit": "pcs", "sort_order": 80},
        {"name": "Car Charger", "unit": "pcs", "sort_order": 90},
    ],
    "services-non-stock": [
        {"name": "Repair Service", "unit": "service", "sort_order": 10},
        {"name": "Installation Service", "unit": "service", "sort_order": 20},
        {"name": "Delivery Fee", "unit": "service", "sort_order": 30},
        {"name": "Consultation Fee", "unit": "service", "sort_order": 40},
        {"name": "Labour Charge", "unit": "service", "sort_order": 50},
        {"name": "Maintenance Service", "unit": "service", "sort_order": 60},
    ],
    "baby-kids": [
        {"name": "Baby Diapers", "unit": "pack", "sort_order": 10},
        {"name": "Baby Clothes", "unit": "pcs", "sort_order": 20},
        {"name": "Baby Lotion", "unit": "pcs", "sort_order": 30},
        {"name": "Feeding Bottle", "unit": "pcs", "sort_order": 40},
        {"name": "Toy", "unit": "pcs", "sort_order": 50},
        {"name": "School Bag", "unit": "pcs", "sort_order": 60},
        {"name": "Kids Shoes", "unit": "pair", "sort_order": 70},
    ],
    "agriculture-inputs": [
        {"name": "Fertilizer (bag)", "unit": "pcs", "sort_order": 10},
        {"name": "Seeds (pack)", "unit": "pack", "sort_order": 20},
        {"name": "Pesticide", "unit": "pcs", "sort_order": 30},
        {"name": "Sprayer", "unit": "pcs", "sort_order": 40},
        {"name": "Hoe", "unit": "pcs", "sort_order": 50},
        {"name": "Watering Can", "unit": "pcs", "sort_order": 60},
        {"name": "Animal Feed (bag)", "unit": "pcs", "sort_order": 70},
    ],
    "sports-fitness": [
        {"name": "Gym Gloves", "unit": "pair", "sort_order": 10},
        {"name": "Dumbbells (pair)", "unit": "pair", "sort_order": 20},
        {"name": "Skipping Rope", "unit": "pcs", "sort_order": 30},
        {"name": "Football", "unit": "pcs", "sort_order": 40},
        {"name": "Sports Shoes", "unit": "pair", "sort_order": 50},
        {"name": "Jersey", "unit": "pcs", "sort_order": 60},
        {"name": "Water Bottle", "unit": "pcs", "sort_order": 70},
    ],
    "mobile-money-services": [
        {"name": "Cash In", "unit": "service", "sort_order": 10},
        {"name": "Cash Out", "unit": "service", "sort_order": 20},
        {"name": "Airtime", "unit": "pcs", "sort_order": 30},
        {"name": "Sim Card", "unit": "pcs", "sort_order": 40},
        {"name": "Transaction Fee", "unit": "service", "sort_order": 50},
        {"name": "Agent Float Adjustment", "unit": "service", "sort_order": 60},
    ],
    "other-custom": [
        {"name": "Custom Item", "unit": "pcs", "sort_order": 10},
    ],
}


# Departments enabled by default when a new mixed-retail workspace is created
DEFAULT_ENABLED_DEPT_SLUGS = [
    "electronics",
    "clothing-fashion",
    "general-goods",
    "other-custom",
]


# ---------------------------------------------------------------------------
# Seed function
# ---------------------------------------------------------------------------

def seed_mixed_retail_catalog() -> dict:
    """
    Seed global (business=None) departments, categories, and product templates.
    Idempotent — safe to run multiple times.

    Returns:
        dict with counts of created/skipped records.
    """
    from inventory.models_mixed_retail import (
        RetailDepartment, RetailCategory, RetailProductTemplate,
    )

    _biz_id, _legacy_local, _legacy_prev = _clear_tenant_locals()
    try:
        return _do_seed(RetailDepartment, RetailCategory, RetailProductTemplate)
    finally:
        _restore_tenant_locals(_biz_id, _legacy_local, _legacy_prev)


def _clear_tenant_locals():
    """Clear thread-local business ID so seed records are created as business=None."""
    try:
        from tenants.models import get_current_business_id, set_current_business_id
        biz_id = get_current_business_id()
        set_current_business_id(None)
    except Exception:
        biz_id = None

    try:
        from tenants.tenants import _local as ll
        _legacy_prev = getattr(ll, "biz_id", None)
        ll.biz_id = None
    except Exception:
        ll = None
        _legacy_prev = None

    return biz_id, ll, _legacy_prev


def _restore_tenant_locals(biz_id, legacy_local, legacy_prev):
    try:
        from tenants.models import set_current_business_id
        set_current_business_id(biz_id)
    except Exception:
        pass

    if legacy_local is not None:
        if legacy_prev is not None:
            legacy_local.biz_id = legacy_prev
        else:
            try:
                del legacy_local.biz_id
            except AttributeError:
                pass


def _do_seed(RetailDepartment, RetailCategory, RetailProductTemplate) -> dict:
    depts_created = depts_skipped = 0
    cats_created = cats_skipped = 0
    templates_created = templates_skipped = 0

    for dept_data in SEED_CATALOG:
        dept, created = RetailDepartment.objects.get_or_create(
            business=None,
            slug=dept_data["slug"],
            defaults={
                "name": dept_data["name"],
                "icon": dept_data.get("icon", "bi-bag"),
                "description": dept_data.get("description", ""),
                "sort_order": dept_data.get("sort_order", 0),
                "is_seeded": True,
                "is_enabled": True,
            },
        )
        if created:
            depts_created += 1
        else:
            depts_skipped += 1
            # Always keep name, icon, description and sort_order in sync
            dept.name = dept_data["name"]
            dept.sort_order = dept_data.get("sort_order", dept.sort_order)
            dept.icon = dept_data.get("icon", dept.icon)
            dept.description = dept_data.get("description", dept.description)
            dept.save(update_fields=["name", "sort_order", "icon", "description"])

        for cat_data in dept_data.get("categories", []):
            _, cat_created = RetailCategory.objects.get_or_create(
                department=dept,
                business=None,
                slug=cat_data["slug"],
                defaults={
                    "name": cat_data["name"],
                    "sort_order": cat_data.get("sort_order", 0),
                    "is_seeded": True,
                    "is_enabled": True,
                },
            )
            if cat_created:
                cats_created += 1
            else:
                cats_skipped += 1

        for tpl_data in PRODUCT_TEMPLATE_CATALOG.get(dept_data["slug"], []):
            _, tpl_created = RetailProductTemplate.objects.get_or_create(
                department=dept,
                name=tpl_data["name"],
                defaults={
                    "suggested_unit": tpl_data.get("unit", "pcs"),
                    "sort_order": tpl_data.get("sort_order", 0),
                    "is_active": True,
                },
            )
            if tpl_created:
                templates_created += 1
            else:
                templates_skipped += 1

    return {
        "depts_created": depts_created,
        "depts_skipped": depts_skipped,
        "cats_created": cats_created,
        "cats_skipped": cats_skipped,
        "templates_created": templates_created,
        "templates_skipped": templates_skipped,
    }


# ---------------------------------------------------------------------------
# Per-business defaults
# ---------------------------------------------------------------------------

def ensure_mixed_retail_defaults(business) -> None:
    """
    Ensure a Mixed Retail workspace has department enrollment records.
    Called when a new mixed-retail business is created or switched into.

    - Creates RetailBusinessDepartment rows for all global seeded departments
      (disabled by default) if they do not yet exist.
    - Enables the DEFAULT_ENABLED_DEPT_SLUGS.
    - Never duplicates records (idempotent).
    """
    from inventory.models_mixed_retail import RetailDepartment, RetailBusinessDepartment

    global_depts = list(
        RetailDepartment.objects.filter(business=None, is_seeded=True)
    )
    if not global_depts:
        # Seed first if catalog missing
        seed_mixed_retail_catalog()
        global_depts = list(
            RetailDepartment.objects.filter(business=None, is_seeded=True)
        )

    for dept in global_depts:
        should_enable = dept.slug in DEFAULT_ENABLED_DEPT_SLUGS
        enrollment, created = RetailBusinessDepartment.objects.get_or_create(
            business=business,
            department=dept,
            defaults={"is_enabled": should_enable},
        )
        if created and should_enable:
            pass  # Already set via defaults
        elif not created and should_enable and not enrollment.is_enabled:
            # First-time enable for default depts (migration/upgrade scenario)
            enrollment.is_enabled = True
            enrollment.save(update_fields=["is_enabled"])


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_departments_for_business(business) -> list:
    """
    Returns enabled departments for a business:
    - Global seeded depts the business has enabled via RetailBusinessDepartment
    - Business-specific custom departments (always shown if is_enabled)

    Falls back gracefully if RetailBusinessDepartment table does not exist yet.
    """
    from inventory.models_mixed_retail import RetailDepartment
    from django.db.models import Q

    try:
        from inventory.models_mixed_retail import RetailBusinessDepartment
        enabled_global_ids = list(
            RetailBusinessDepartment.objects.filter(
                business=business, is_enabled=True
            ).values_list("department_id", flat=True)
        )
    except Exception:
        # Table might not exist during first migration; fall back to legacy behaviour
        enabled_global_ids = list(
            RetailDepartment.objects.filter(
                business=None, is_seeded=True, is_enabled=True
            ).values_list("id", flat=True)
        )

    return list(
        RetailDepartment.objects.filter(
            Q(business=None, is_seeded=True, id__in=enabled_global_ids)
            | Q(business=business, is_enabled=True)
        ).order_by("sort_order", "name")
    )


def get_all_departments_with_status(business) -> list:
    """
    Returns all global seeded departments annotated with business-specific
    is_enabled status, plus custom departments.

    Each item is a dict:
    {
        "dept": RetailDepartment,
        "is_enabled": bool,
        "template_count": int,
        "category_count": int,
        "is_custom": bool,
    }
    """
    from inventory.models_mixed_retail import RetailDepartment, RetailBusinessDepartment

    # Build enabled_map for global depts
    try:
        enrollments = {
            e.department_id: e.is_enabled
            for e in RetailBusinessDepartment.objects.filter(business=business)
        }
    except Exception:
        enrollments = {}

    global_depts = list(
        RetailDepartment.objects.filter(
            business=None, is_seeded=True
        ).prefetch_related("product_templates").order_by("sort_order", "name")
    )

    custom_depts = list(
        RetailDepartment.objects.filter(
            business=business
        ).order_by("sort_order", "name")
    )

    result = []
    for dept in global_depts:
        result.append({
            "dept": dept,
            "is_enabled": enrollments.get(dept.id, False),
            "template_count": dept.product_templates.filter(is_active=True).count(),
            "category_count": dept.categories.filter(business=None, is_enabled=True).count(),
            "is_custom": False,
        })

    for dept in custom_depts:
        result.append({
            "dept": dept,
            "is_enabled": dept.is_enabled,
            "template_count": 0,
            "category_count": dept.categories.filter(is_enabled=True).count(),
            "is_custom": True,
        })

    return result


def get_categories_for_department(department, business=None) -> list:
    """Returns all enabled categories for a department (global + business-specific)."""
    from inventory.models_mixed_retail import RetailCategory
    from django.db.models import Q

    qs = RetailCategory.objects.filter(department=department, is_enabled=True)
    if business:
        qs = qs.filter(Q(business=None) | Q(business=business))
    else:
        qs = qs.filter(business=None)
    return list(qs.order_by("sort_order", "name"))


def get_product_templates_for_department(department) -> list:
    """Returns active product templates for a seeded department."""
    from inventory.models_mixed_retail import RetailProductTemplate
    return list(
        RetailProductTemplate.objects.filter(
            department=department, is_active=True
        ).order_by("sort_order", "name")
    )
