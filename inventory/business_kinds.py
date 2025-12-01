from django.db import models


class BusinessKind(models.TextChoices):
    PHONES = "phones", "Phones & Electronics"
    LIQUOR = "liquor", "Liquor / Bar"
    GROCERY = "grocery", "Grocery / General"
    PHARMACY = "pharmacy", "Pharmacy"
    CLOTHING = "clothing", "Clothing"
    GYM = "gym", "Gym / Fitness"


__all__ = ["BusinessKind"]

