from django.contrib import admin

from .models import District, Region, TraditionalAuthority


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "region")
    list_filter = ("region",)
    search_fields = ("name", "region__name")


@admin.register(TraditionalAuthority)
class TraditionalAuthorityAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "region_name")
    list_filter = ("district__region", "district")
    search_fields = ("name", "district__name", "district__region__name")

    @admin.display(ordering="district__region__name", description="Region")
    def region_name(self, obj):
        return obj.district.region.name
