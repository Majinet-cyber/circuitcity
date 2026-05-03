from django import template

from inventory.services.marketplace_media import (
    listing_media,
    marketplace_image_url,
    placeholder_icon,
)
from inventory.services.media_safety import safe_field_url

register = template.Library()


@register.filter
def listing_card_media(listing):
    return listing_media(listing)


@register.filter
def marketplace_image_src(image_obj):
    return marketplace_image_url(image_obj)


@register.filter
def marketplace_placeholder(vertical):
    return placeholder_icon(vertical)


@register.filter
def safe_media_url(field_file):
    return safe_field_url(field_file)
