# inventory/electronics_catalog_seed.py
"""
Seed laptop and desktop product templates for PHONES/Electronics businesses.

Provides 4 sample models per brand for LAPTOP and DESKTOP categories.
Users can edit/delete these; they are starter templates only.
"""
from __future__ import annotations

from django.db import transaction

from tenants.models import Business


# Laptop brands: Dell, Lenovo, Apple/MacBook, Samsung, Toshiba, HP, Acer, Asus
LAPTOP_BRANDS = ["Dell", "Lenovo", "Apple", "HP", "Samsung", "Toshiba", "Acer", "Asus"]

# 4 sample laptop models per brand (realistic specs)
LAPTOP_TEMPLATES = [
    {"brand": "Dell", "model_name": "Latitude 5420", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i5-1135G7", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "Dell", "model_name": "XPS 15", "ram_str": "32GB", "storage_str": "1TB SSD", "cpu": "Intel i7-12700H", "screen_size": "15.6\"", "gpu": "NVIDIA RTX 3050", "os": "Windows 11"},
    {"brand": "Dell", "model_name": "Inspiron 15 3000", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i3-1115G4", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Dell", "model_name": "Vostro 3520", "ram_str": "8GB", "storage_str": "512GB SSD", "cpu": "Intel i5-1235U", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Lenovo", "model_name": "ThinkPad X1 Carbon", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-1260P", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "Lenovo", "model_name": "IdeaPad Slim 3", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "AMD Ryzen 5 5500U", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Lenovo", "model_name": "ThinkPad E14", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i5-1235U", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "Lenovo", "model_name": "Legion 5", "ram_str": "16GB", "storage_str": "1TB SSD", "cpu": "AMD Ryzen 7 5800H", "screen_size": "15.6\"", "gpu": "NVIDIA RTX 3060", "os": "Windows 11"},
    {"brand": "Apple", "model_name": "MacBook Air M2", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Apple M2", "screen_size": "13.6\"", "os": "macOS"},
    {"brand": "Apple", "model_name": "MacBook Pro 14", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Apple M3 Pro", "screen_size": "14.2\"", "os": "macOS"},
    {"brand": "Apple", "model_name": "MacBook Pro 16", "ram_str": "32GB", "storage_str": "1TB SSD", "cpu": "Apple M3 Max", "screen_size": "16.2\"", "os": "macOS"},
    {"brand": "Apple", "model_name": "MacBook Air M1", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Apple M1", "screen_size": "13.3\"", "os": "macOS"},
    {"brand": "HP", "model_name": "Pavilion 15", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-1235U", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "HP", "model_name": "EliteBook 840", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-1255U", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "HP", "model_name": "Victus 16", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "AMD Ryzen 5 5600H", "screen_size": "16.1\"", "gpu": "NVIDIA GTX 1650", "os": "Windows 11"},
    {"brand": "HP", "model_name": "Laptop 15s", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i3-1215U", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Samsung", "model_name": "Galaxy Book2 Pro", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-1260P", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Samsung", "model_name": "Galaxy Book Go", "ram_str": "8GB", "storage_str": "128GB eUFS", "cpu": "Snapdragon 7c", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "Samsung", "model_name": "Galaxy Book3 360", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i5-1340P", "screen_size": "13.3\"", "os": "Windows 11"},
    {"brand": "Samsung", "model_name": "Galaxy Book Pro", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-1135G7", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Toshiba", "model_name": "Tecra A50", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i5-1135G7", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Toshiba", "model_name": "Portégé X30", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-1165G7", "screen_size": "13.3\"", "os": "Windows 11"},
    {"brand": "Toshiba", "model_name": "Satellite Pro C50", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i3-1115G4", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Toshiba", "model_name": "Dynabook Tecra", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-1235U", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "Acer", "model_name": "Aspire 5", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "AMD Ryzen 5 5500U", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Acer", "model_name": "Swift 3", "ram_str": "8GB", "storage_str": "512GB SSD", "cpu": "Intel i5-1235U", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "Acer", "model_name": "Nitro 5", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i5-12500H", "screen_size": "15.6\"", "gpu": "NVIDIA RTX 3050", "os": "Windows 11"},
    {"brand": "Acer", "model_name": "TravelMate P4", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-1255U", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "Asus", "model_name": "VivoBook 15", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i3-1215U", "screen_size": "15.6\"", "os": "Windows 11"},
    {"brand": "Asus", "model_name": "ZenBook 14", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-1260P", "screen_size": "14\"", "os": "Windows 11"},
    {"brand": "Asus", "model_name": "ROG Strix G15", "ram_str": "16GB", "storage_str": "1TB SSD", "cpu": "AMD Ryzen 7 6800H", "screen_size": "15.6\"", "gpu": "NVIDIA RTX 3060", "os": "Windows 11"},
    {"brand": "Asus", "model_name": "ExpertBook B1", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-1235U", "screen_size": "14\"", "os": "Windows 11"},
]

DESKTOP_BRANDS = ["Dell", "Lenovo", "Apple", "HP", "Samsung", "Toshiba", "Acer", "Asus"]

DESKTOP_TEMPLATES = [
    {"brand": "Dell", "model_name": "OptiPlex 3090", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-10505", "os": "Windows 11"},
    {"brand": "Dell", "model_name": "OptiPlex 7090", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-11700", "os": "Windows 11"},
    {"brand": "Dell", "model_name": "Vostro 3888", "ram_str": "8GB", "storage_str": "1TB HDD", "cpu": "Intel i3-10100", "os": "Windows 11"},
    {"brand": "Dell", "model_name": "Precision 3660", "ram_str": "32GB", "storage_str": "1TB SSD", "cpu": "Intel i7-13700", "gpu": "NVIDIA T1000", "os": "Windows 11"},
    {"brand": "Lenovo", "model_name": "ThinkCentre M75q", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "AMD Ryzen 5 5650GE", "os": "Windows 11"},
    {"brand": "Lenovo", "model_name": "IdeaCentre 5", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i5-12400", "os": "Windows 11"},
    {"brand": "Lenovo", "model_name": "ThinkStation P350", "ram_str": "32GB", "storage_str": "1TB SSD", "cpu": "Intel i7-12700", "gpu": "NVIDIA T400", "os": "Windows 11"},
    {"brand": "Lenovo", "model_name": "Legion T5", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "AMD Ryzen 5 5600G", "gpu": "NVIDIA RTX 3060", "os": "Windows 11"},
    {"brand": "Apple", "model_name": "iMac 24\" M3", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Apple M3", "screen_size": "24\"", "os": "macOS"},
    {"brand": "Apple", "model_name": "Mac mini M2", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Apple M2", "os": "macOS"},
    {"brand": "Apple", "model_name": "Mac Studio M2 Max", "ram_str": "32GB", "storage_str": "512GB SSD", "cpu": "Apple M2 Max", "os": "macOS"},
    {"brand": "Apple", "model_name": "iMac 24\" M1", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Apple M1", "screen_size": "24\"", "os": "macOS"},
    {"brand": "HP", "model_name": "ProDesk 400 G8", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-10505", "os": "Windows 11"},
    {"brand": "HP", "model_name": "Pavilion Desktop", "ram_str": "8GB", "storage_str": "512GB SSD", "cpu": "Intel i5-12400", "os": "Windows 11"},
    {"brand": "HP", "model_name": "EliteDesk 800 G8", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-11700", "os": "Windows 11"},
    {"brand": "HP", "model_name": "M01 F1033w", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "AMD Ryzen 5 5600G", "os": "Windows 11"},
    {"brand": "Samsung", "model_name": "DM500", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-10400", "os": "Windows 11"},
    {"brand": "Samsung", "model_name": "DP700", "ram_str": "8GB", "storage_str": "512GB SSD", "cpu": "Intel i5-12400", "os": "Windows 11"},
    {"brand": "Samsung", "model_name": "DB400", "ram_str": "4GB", "storage_str": "128GB SSD", "cpu": "Intel Celeron", "os": "Windows 11"},
    {"brand": "Samsung", "model_name": "DP900", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-12700", "os": "Windows 11"},
    {"brand": "Toshiba", "model_name": "Dynabook Desktop", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-10400", "os": "Windows 11"},
    {"brand": "Toshiba", "model_name": "Tecra Desktop", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-11700", "os": "Windows 11"},
    {"brand": "Toshiba", "model_name": "Satellite Desktop", "ram_str": "8GB", "storage_str": "1TB HDD", "cpu": "Intel i3-10100", "os": "Windows 11"},
    {"brand": "Toshiba", "model_name": "Portégé Desktop", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i5-12500", "os": "Windows 11"},
    {"brand": "Acer", "model_name": "Aspire C24", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-1235U", "screen_size": "23.8\"", "os": "Windows 11"},
    {"brand": "Acer", "model_name": "Veriton N", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-10505", "os": "Windows 11"},
    {"brand": "Acer", "model_name": "Predator Orion 3000", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i5-12400F", "gpu": "NVIDIA RTX 3060", "os": "Windows 11"},
    {"brand": "Acer", "model_name": "Aspire X", "ram_str": "8GB", "storage_str": "512GB SSD", "cpu": "Intel i5-12400", "os": "Windows 11"},
    {"brand": "Asus", "model_name": "ExpertCenter D5", "ram_str": "8GB", "storage_str": "256GB SSD", "cpu": "Intel i5-12400", "os": "Windows 11"},
    {"brand": "Asus", "model_name": "ROG Strix G22", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "Intel i7-13700F", "gpu": "NVIDIA RTX 4060", "os": "Windows 11"},
    {"brand": "Asus", "model_name": "ProArt Station", "ram_str": "32GB", "storage_str": "1TB SSD", "cpu": "Intel i9-13900", "gpu": "NVIDIA RTX 4070", "os": "Windows 11"},
    {"brand": "Asus", "model_name": "Mini PC PN51", "ram_str": "16GB", "storage_str": "512GB SSD", "cpu": "AMD Ryzen 7 5700U", "os": "Windows 11"},
]


def seed_laptop_desktop_catalog(business: Business, category: str, created_by=None) -> int:
    """Seed laptop or desktop catalog. category: 'LAPTOP' or 'DESKTOP'. Returns created count."""
    from inventory.models_phone_products import PhoneProductCatalog, ElectronicsCategory

    if category not in (ElectronicsCategory.LAPTOP, ElectronicsCategory.DESKTOP):
        return 0

    templates = LAPTOP_TEMPLATES if category == ElectronicsCategory.LAPTOP else DESKTOP_TEMPLATES
    created_count = 0

    for t in templates:
        _, created = PhoneProductCatalog.objects.get_or_create(
            business=business,
            category=category,
            brand=t["brand"],
            model_name=t["model_name"],
            ram_gb=0,
            rom_gb=0,
            ram_str=t.get("ram_str", ""),
            storage_str=t.get("storage_str", ""),
            defaults={
                "cpu": t.get("cpu", ""),
                "screen_size": t.get("screen_size", ""),
                "gpu": t.get("gpu", ""),
                "os": t.get("os", ""),
                "is_active": True,
                "created_by": created_by,
            },
        )
        if created:
            created_count += 1

    return created_count


@transaction.atomic
def seed_electronics_catalog(business: Business, created_by=None) -> dict:
    """Seed both laptop and desktop catalogs. Returns {'laptops': n, 'desktops': m}."""
    laptops = seed_laptop_desktop_catalog(business, "LAPTOP", created_by=created_by)
    desktops = seed_laptop_desktop_catalog(business, "DESKTOP", created_by=created_by)
    return {"laptops": laptops, "desktops": desktops}
