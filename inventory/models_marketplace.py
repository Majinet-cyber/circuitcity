# inventory/models_marketplace.py
"""
Marketplace models for public business listings and enquiries.

This module implements a minimal, safe marketplace where businesses can:
- Create public listings (products/services) with photos/videos
- Receive enquiries from public users
- Manage their public-facing business page

Security:
- All media uploads are validated (size, type)
- Only active listings are shown publicly
- Permissions enforced: only managers/admins can create/edit listings
- No private business data exposed
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, EmailValidator
from django.db import models
from django.utils import timezone

from tenants.models import Business

User = settings.AUTH_USER_MODEL


def validate_marketplace_media_size(file):
    """
    Validate media file size for marketplace listings.
    Max 10 MB to allow videos while preventing abuse.
    """
    MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    if file.size > MAX_SIZE:
        raise ValidationError(f"File size exceeds 10 MB limit. Current size: {file.size / (1024 * 1024):.1f} MB")


def validate_marketplace_media_type(file):
    """
    Validate media file type for marketplace listings.
    Allow images (JPEG, PNG, WEBP) and videos (MP4, WEBM).
    No SVG (XSS risk), no GIF (can be large).
    """
    ALLOWED_TYPES = {
        'image/jpeg',
        'image/png',
        'image/webp',
        'video/mp4',
        'video/webm',
    }
    
    content_type = getattr(file, 'content_type', '')
    if not content_type:
        raise ValidationError("Unable to determine file type.")
    
    if content_type not in ALLOWED_TYPES:
        raise ValidationError(
            f"Unsupported file type: {content_type}. "
            "Allowed: JPEG, PNG, WEBP images or MP4, WEBM videos."
        )


def marketplace_media_upload_path(instance, filename):
    """
    Generate safe upload path for marketplace media.
    Pattern: marketplace/<business_id>/<year>/<month>/<filename>
    """
    # Sanitize filename (remove path traversal attempts)
    filename = os.path.basename(filename)
    
    # Use business ID and date for organization
    now = timezone.now()
    return f"marketplace/{instance.business.id}/{now.year}/{now.month:02d}/{filename}"


class MarketplaceListing(models.Model):
    """
    A public listing (product/service) that appears on the marketplace.
    
    Businesses can create listings to showcase their offerings.
    Public users can view listings and submit enquiries.
    """
    
    # Business relationship
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='marketplace_listings',
        db_index=True,
        help_text="Business that owns this listing"
    )
    
    # Vertical tag (optional, for filtering)
    vertical = models.CharField(
        max_length=20,
        blank=True,
        default='',
        db_index=True,
        help_text="Business vertical (phones, gym, pharmacy, etc.)"
    )
    
    # Listing content
    title = models.CharField(
        max_length=200,
        help_text="Product or service name"
    )
    
    description = models.TextField(
        blank=True,
        default='',
        help_text="Detailed description (optional)"
    )
    
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Price in business currency (optional)"
    )
    
    # Media (image or video)
    media_file = models.FileField(
        upload_to=marketplace_media_upload_path,
        null=True,
        blank=True,
        validators=[validate_marketplace_media_size, validate_marketplace_media_type],
        help_text="Product photo or video (max 10 MB)"
    )
    
    # Status
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Only active listings appear on marketplace"
    )
    
    # Metadata
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='marketplace_listings_created',
        help_text="User who created this listing"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'is_active']),
            models.Index(fields=['vertical', 'is_active']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.business.name})"
    
    @property
    def is_image(self) -> bool:
        """Check if media is an image."""
        if not self.media_file:
            return False
        content_type = getattr(self.media_file, 'content_type', '')
        return content_type.startswith('image/')
    
    @property
    def is_video(self) -> bool:
        """Check if media is a video."""
        if not self.media_file:
            return False
        content_type = getattr(self.media_file, 'content_type', '')
        return content_type.startswith('video/')


class MarketplaceEnquiry(models.Model):
    """
    An enquiry submitted by a public user about a marketplace listing.
    
    Public users can submit enquiries without logging in.
    Managers can view enquiries in their dashboard.
    """
    
    # Relationships
    listing = models.ForeignKey(
        MarketplaceListing,
        on_delete=models.CASCADE,
        related_name='enquiries',
        db_index=True,
        help_text="Listing this enquiry is about"
    )
    
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name='marketplace_enquiries',
        db_index=True,
        help_text="Business receiving this enquiry (denormalized for easy queries)"
    )
    
    # Enquirer information
    email = models.EmailField(
        validators=[EmailValidator()],
        help_text="Enquirer's email (required)"
    )
    
    phone = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text="Enquirer's phone number (optional)"
    )
    
    name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text="Enquirer's name (optional)"
    )
    
    message = models.TextField(
        blank=True,
        default='',
        help_text="Enquiry message (optional)"
    )
    
    # Status
    is_read = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether manager has read this enquiry"
    )
    
    # Metadata
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When manager marked this as read"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Marketplace enquiries'
        indexes = [
            models.Index(fields=['business', 'is_read']),
            models.Index(fields=['listing', '-created_at']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"Enquiry from {self.email} about {self.listing.title}"
    
    def mark_as_read(self):
        """Mark this enquiry as read."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

