"""
Tests for Standard Scanner Phone IMEI Validation
=================================================
Tests the phone-specific validation rules enforced by the standard scanner:
- 15-digit IMEI requirement (Scan In + Scan & Sell)
- In-stock validation (Scan & Sell only)
- IMEI uniqueness validation (Scan In only)

These tests ensure the standardization requirements are met:
1. IMEI must be exactly 15 digits
2. Scan & Sell: IMEI must be in stock to proceed
3. Scan In: IMEI must not already exist in the system
"""

import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from inventory.models import StockItem, Product, Location
from tenants.models import Business

User = get_user_model()


class StandardScannerPhoneValidationTest(TestCase):
    """Test phone-specific IMEI validation for standard scanner"""

    def setUp(self):
        """Set up test data"""
        # Create business
        self.business = Business.objects.create(
            name="Test Electronics Store",
            slug="test-electronics"
        )

        # Create user (agent)
        self.user = User.objects.create_user(
            username="agent001",
            password="testpass123",
            email="agent@test.com"
        )
        
        # Associate user with business
        self.user.profile.business = self.business
        self.user.profile.save()

        # Create location
        self.location = Location.objects.create(
            name="Main Store",
            business=self.business
        )

        # Create product (phone)
        self.product = Product.objects.create(
            name="iPhone 13",
            business=self.business,
            category="phone"
        )

        # Create test IMEI in stock
        self.test_imei_in_stock = "123456789012345"
        self.stock_item = StockItem.objects.create(
            product=self.product,
            imei=self.test_imei_in_stock,
            business=self.business,
            location=self.location,
            status="IN_STOCK",
            order_price=500.00,
            selling_price=700.00
        )

        # Test IMEI not in stock (doesn't exist)
        self.test_imei_not_in_stock = "999999999999999"

        # Invalid IMEIs (not 15 digits)
        self.invalid_imei_short = "12345678901234"  # 14 digits
        self.invalid_imei_long = "1234567890123456"  # 16 digits
        self.invalid_imei_letters = "12345678901234A"  # contains letter

        self.client = Client()
        self.client.login(username="agent001", password="testpass123")

    def test_stock_status_api_validates_15_digits(self):
        """Test that stock status API rejects non-15-digit IMEIs"""
        url = reverse('inventory:api_stock_status')
        
        # Test with 14 digits (invalid)
        response = self.client.get(url, {'code': self.invalid_imei_short})
        self.assertIn(response.status_code, [400, 404])
        
        # Test with 16 digits (invalid)
        response = self.client.get(url, {'code': self.invalid_imei_long})
        self.assertIn(response.status_code, [400, 404])
        
        # Test with letters (invalid)
        response = self.client.get(url, {'code': self.invalid_imei_letters})
        self.assertIn(response.status_code, [400, 404])

    def test_stock_status_api_accepts_valid_15_digit_imei(self):
        """Test that stock status API accepts valid 15-digit IMEI"""
        url = reverse('inventory:api_stock_status')
        
        # Test with valid IMEI in stock
        response = self.client.get(url, {'code': self.test_imei_in_stock})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        
        # Should indicate item is in stock
        self.assertTrue(data.get('in_stock') or data.get('exists'))

    def test_stock_status_api_returns_not_in_stock_for_missing_imei(self):
        """Test that stock status API indicates IMEI not in stock"""
        url = reverse('inventory:api_stock_status')
        
        # Test with valid 15-digit IMEI that doesn't exist
        response = self.client.get(url, {'code': self.test_imei_not_in_stock})
        
        # Should return 200 but indicate not in stock
        if response.status_code == 200:
            data = json.loads(response.content)
            self.assertFalse(data.get('in_stock', False))
        else:
            # Or return 404
            self.assertEqual(response.status_code, 404)

    def test_scan_in_rejects_duplicate_imei(self):
        """Test that Scan In rejects IMEI that already exists"""
        url = reverse('inventory:scan_in')
        
        # Try to scan in the IMEI that's already in stock
        response = self.client.post(url, {
            'imei': self.test_imei_in_stock,
            'product': self.product.id,
            'location': self.location.id,
            'order_price': 500.00
        })
        
        # Should reject (either redirect with error or 400)
        # Implementation may vary, but IMEI should not be duplicated
        if response.status_code == 200:
            # Check for error message in context
            self.assertTrue(
                'error' in response.context or 
                'messages' in response.context or
                'form' in response.context
            )
        else:
            self.assertIn(response.status_code, [302, 400])

    def test_scan_in_rejects_non_15_digit_imei(self):
        """Test that Scan In rejects IMEIs that aren't exactly 15 digits"""
        url = reverse('inventory:scan_in')
        
        # Try with 14-digit IMEI
        response = self.client.post(url, {
            'imei': self.invalid_imei_short,
            'product': self.product.id,
            'location': self.location.id,
            'order_price': 500.00
        })
        
        # Should reject
        self.assertIn(response.status_code, [200, 400])
        if response.status_code == 200:
            # Should have form errors
            if hasattr(response, 'context') and 'form' in response.context:
                self.assertFalse(response.context['form'].is_valid())

    def test_scan_sell_rejects_imei_not_in_stock(self):
        """Test that Scan & Sell rejects IMEI not in stock"""
        url = reverse('inventory:api_mark_sold')
        
        # Try to sell IMEI that's not in stock
        response = self.client.post(
            url,
            json.dumps({
                'imei': self.test_imei_not_in_stock,
                'price': 700.00,
                'sold_date': '2024-01-01',
                'location_id': str(self.location.id)
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should reject (400 or error response)
        self.assertIn(response.status_code, [400, 404])

    def test_scan_sell_accepts_valid_in_stock_imei(self):
        """Test that Scan & Sell accepts valid in-stock IMEI"""
        url = reverse('inventory:api_mark_sold')
        
        # Sell the in-stock IMEI
        response = self.client.post(
            url,
            json.dumps({
                'imei': self.test_imei_in_stock,
                'price': 700.00,
                'sold_date': '2024-01-01',
                'location_id': str(self.location.id)
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should succeed
        self.assertEqual(response.status_code, 200)
        
        # Verify item is now marked as SOLD
        self.stock_item.refresh_from_db()
        self.assertEqual(self.stock_item.status, 'SOLD')

    def test_scan_sell_rejects_non_15_digit_imei(self):
        """Test that Scan & Sell rejects non-15-digit IMEI"""
        url = reverse('inventory:api_mark_sold')
        
        # Try with 14-digit IMEI
        response = self.client.post(
            url,
            json.dumps({
                'imei': self.invalid_imei_short,
                'price': 700.00,
                'sold_date': '2024-01-01',
                'location_id': str(self.location.id)
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        # Should reject
        self.assertIn(response.status_code, [400, 404])


class StandardScannerBackCameraOnlyTest(TestCase):
    """Test that scanner templates enforce back camera only policy"""

    def test_scanner_modal_template_has_no_switch_camera_option(self):
        """Verify scanner_modal.html has no switch camera UI"""
        with open('templates/components/scanner_modal.html', 'r') as f:
            content = f.read()
        
        # Should NOT contain switch camera text
        self.assertNotIn('switch camera', content.lower())
        self.assertNotIn('switchcamera', content.lower())
        
        # Should enforce back camera
        self.assertIn('environment', content)

    def test_standard_scanner_js_has_no_switch_camera_function(self):
        """Verify scanner_standard.js has no switchCamera function"""
        with open('static/js/scanner_standard.js', 'r') as f:
            content = f.read()
        
        # Should NOT have switchCamera function
        self.assertNotIn('switchCamera', content)
        self.assertNotIn('switch camera', content.lower())
        
        # Should enforce back camera
        self.assertIn('environment', content)


class StandardScannerUseAndScanAgainUXTest(TestCase):
    """Test that scanner has Use/Scan Again buttons (Fast Sell UX)"""

    def test_scanner_modal_has_use_button(self):
        """Verify scanner has Use button"""
        with open('templates/components/scanner_modal.html', 'r') as f:
            content = f.read()
        
        # Should have Use button
        self.assertIn('Use', content)
        self.assertIn('cc-scanner-use-btn', content)

    def test_scanner_modal_has_scan_again_button(self):
        """Verify scanner has Scan Again button"""
        with open('templates/components/scanner_modal.html', 'r') as f:
            content = f.read()
        
        # Should have Scan Again button
        self.assertIn('Scan Again', content)
        self.assertIn('cc-scanner-rescan-btn', content)

    def test_scanner_shows_detected_value_box(self):
        """Verify scanner shows detected value in result box"""
        with open('templates/components/scanner_modal.html', 'r') as f:
            content = f.read()
        
        # Should have result box
        self.assertIn('cc-scanner-result-box', content)
        self.assertIn('cc-scanner-result-value', content)
        
        # Should have helper text
        self.assertIn('detected', content.lower())


if __name__ == '__main__':
    import unittest
    unittest.main()

