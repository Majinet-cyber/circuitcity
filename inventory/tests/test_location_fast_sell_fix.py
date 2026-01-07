# inventory/tests/test_location_fast_sell_fix.py
"""
Test that Location queries work without is_active field.
Previously failed with: Cannot resolve keyword 'is_active' into field.

This regression test ensures Location.objects.filter(...) calls
use correct field names (is_default, not is_active).
"""
import pytest
from django.test import TestCase

from inventory.models import Location
from tenants.constants import BusinessKind
from tenants.models import Business


@pytest.mark.django_db
class TestLocationQueryFix(TestCase):
    """Test that Location queries use correct fields."""

    def setUp(self):
        """Create test data."""
        self.business = Business.objects.create(
            name="Test Business",
            slug="test-biz",
            business_kind=BusinessKind.PHONES,
        )

    def test_location_has_no_is_active_field(self):
        """Verify Location model does NOT have is_active field."""
        location = Location.objects.create(
            business=self.business,
            name="Test Location",
        )
        
        # Should NOT have is_active attribute
        assert not hasattr(location, 'is_active')
        
        # Should have is_default instead
        assert hasattr(location, 'is_default')

    def test_cannot_query_by_is_active(self):
        """Location queries by is_active should fail with FieldError."""
        Location.objects.create(
            business=self.business,
            name="Test Store",
        )
        
        # This should raise FieldError
        from django.core.exceptions import FieldError
        with pytest.raises(FieldError) as exc_info:
            Location.objects.filter(
                business=self.business,
                is_active=True
            ).first()
        
        # Error message should mention is_active
        assert "is_active" in str(exc_info.value).lower()

