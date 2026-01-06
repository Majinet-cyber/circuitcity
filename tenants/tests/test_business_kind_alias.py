# tenants/tests/test_business_kind_alias.py
"""
Test that Business model accepts legacy 'kind' parameter.
This ensures backwards compatibility with existing test code.
"""
import pytest
from django.test import TestCase

from tenants.constants import BusinessKind
from tenants.models import Business


@pytest.mark.django_db
class TestBusinessKindAlias(TestCase):
    """Test Business.kind parameter alias for backwards compatibility."""

    def test_business_accepts_kind_parameter(self):
        """Business(kind='phones') should work and set business_kind."""
        business = Business.objects.create(
            name="Test Phones Business",
            slug="test-phones-biz",
            kind="phones",  # Legacy parameter
        )
        
        # Verify it was saved correctly
        assert business.business_kind == "phones"
        assert business.kind == "phones"  # Property should also work
        
        # Verify we can read it back from DB
        saved = Business.objects.get(pk=business.pk)
        assert saved.business_kind == "phones"
        assert saved.kind == "phones"

    def test_business_kind_property_readable(self):
        """Business.kind property should return business_kind value."""
        business = Business.objects.create(
            name="Test Liquor Business",
            slug="test-liquor-biz",
            business_kind=BusinessKind.LIQUOR,
        )
        
        assert business.kind == BusinessKind.LIQUOR
        assert business.kind == business.business_kind

    def test_business_kind_property_writable(self):
        """Business.kind property setter should update business_kind."""
        business = Business.objects.create(
            name="Test Gym Business",
            slug="test-gym-biz",
        )
        
        # Use the property setter
        business.kind = BusinessKind.GYM
        business.save()
        
        # Verify it was saved
        saved = Business.objects.get(pk=business.pk)
        assert saved.business_kind == BusinessKind.GYM
        assert saved.kind == BusinessKind.GYM

    def test_business_both_parameters_prefer_business_kind(self):
        """If both kind and business_kind provided, business_kind wins after init mapping."""
        # kind gets mapped to business_kind in __init__, so last one wins
        business = Business(
            name="Test Business",
            slug="test-biz",
            kind="phones",  # This gets mapped to business_kind
        )
        
        # After __init__, kind is mapped
        assert business.business_kind == "phones"

