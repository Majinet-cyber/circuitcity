from django.db import models


class Region(models.Model):
    name = models.CharField(max_length=80, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class District(models.Model):
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="districts")
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["region__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["region", "name"], name="unique_district_per_region"),
        ]

    def __str__(self):
        return f"{self.name}, {self.region.name}"


class TraditionalAuthority(models.Model):
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name="traditional_authorities")
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["district__region__name", "district__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["district", "name"], name="unique_ta_per_district"),
        ]

    def __str__(self):
        return f"{self.name}, {self.district.name}"
