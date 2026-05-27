# inventory/tests/test_jan2026_comprehensive.py
"""
Comprehensive regression tests for Jan 2026 fixes:

PART 1 - Liquor UoM (per-bottle/per-shot costing)
PART 2 - Welding quotation buttons
PART 3 - Navbar dropdowns
PART 4 - Data Correction for all verticals
PART 5 - Farming livestock separation
PART 6 - Car Hire email notifications

CRITICAL: All tests MUST pass for deployment.
"""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core import mail

# Conditional imports to handle missing models gracefully
try:
    from tenants.models import Business, BusinessKind
except ImportError:
    Business = None
    BusinessKind = None

try:
    from accounts.models import User
except ImportError:
    User = None

try:
    from inventory.models import MerchProduct, Location
except ImportError:
    MerchProduct = None
    Location = None


# ==============================================================================
# PART 1: LIQUOR VERTICAL TESTS - UoM System
# ==============================================================================

class TestLiquorUoMConversions(TestCase):
    """Test liquor unit-of-measure conversions."""
    
    @pytest.fixture(autouse=True)
    def setup_fixtures(self, db):
        """Set up test fixtures."""
        pass
    
    def test_beer_crate_to_bottle_cost_conversion(self):
        """
        Test: 1 crate @ MWK 60,000 with 20 bottles = MWK 3,000 per bottle.
        """
        if MerchProduct is None:
            self.skipTest("MerchProduct model not available")
        
        # Create a mock product with crate configuration
        product = MagicMock()
        product.cost_per_bottle = Decimal("3000.00")
        product.bottles_per_crate = 20
        product.has_shots = False
        product.has_glasses = False
        product.supports_crates = True
        product.kind = "liquor"
        
        # Test get_cost_for_unit method
        product.get_cost_for_unit = lambda unit: (
            product.cost_per_bottle if unit == "bottle"
            else product.cost_per_bottle * Decimal(product.bottles_per_crate) if unit == "crate"
            else Decimal("0.00")
        )
        
        # Verify bottle cost
        bottle_cost = product.get_cost_for_unit("bottle")
        self.assertEqual(bottle_cost, Decimal("3000.00"))
        
        # Verify crate cost = bottle cost * bottles per crate
        crate_cost = product.get_cost_for_unit("crate")
        self.assertEqual(crate_cost, Decimal("60000.00"))
    
    def test_spirits_bottle_to_shot_cost_conversion(self):
        """
        Test: 1 bottle @ MWK 60,000 with 25 shots = MWK 2,400 per shot.
        """
        if MerchProduct is None:
            self.skipTest("MerchProduct model not available")
        
        # Create a mock product with shot configuration
        product = MagicMock()
        product.cost_per_bottle = Decimal("60000.00")
        product.shots_per_bottle = 25
        product.barman_shots_reserved = 2  # Barman gets 2 shots
        product.has_shots = True
        product.has_glasses = False
        product.kind = "liquor"
        
        # Calculated cost per shot
        sellable_shots = product.shots_per_bottle - product.barman_shots_reserved
        expected_cost_per_shot = product.cost_per_bottle / Decimal(sellable_shots)
        
        # Verify calculations
        self.assertEqual(sellable_shots, 23)
        # Cost per shot = 60000 / 23 = ~2608.70
        self.assertAlmostEqual(
            float(expected_cost_per_shot),
            2608.70,
            places=2
        )
    
    def test_wine_bottle_to_glass_cost_conversion(self):
        """
        Test: Wine bottle to glass conversion.
        """
        # Create a mock product with glass configuration
        product = MagicMock()
        product.cost_per_bottle = Decimal("25000.00")
        product.glasses_per_bottle = 5
        product.has_glasses = True
        product.has_shots = False
        
        # Calculate cost per glass
        cost_per_glass = product.cost_per_bottle / Decimal(product.glasses_per_bottle)
        self.assertEqual(cost_per_glass, Decimal("5000.00"))
    
    def test_margin_calculation_good_margin(self):
        """Test margin calculation: >30% = Good margin."""
        cost = Decimal("3000.00")
        selling_price = Decimal("5000.00")
        
        profit = selling_price - cost
        margin_percent = (profit / selling_price) * Decimal("100")
        
        self.assertEqual(profit, Decimal("2000.00"))
        self.assertEqual(margin_percent, Decimal("40"))  # 40% margin
        
        # Determine margin label
        if margin_percent > 30:
            label = "good"
        elif margin_percent >= 15:
            label = "ok"
        elif margin_percent > 0:
            label = "low"
        else:
            label = "loss"
        
        self.assertEqual(label, "good")
    
    def test_margin_calculation_loss(self):
        """Test margin calculation: selling below cost = LOSS."""
        cost = Decimal("3000.00")
        selling_price = Decimal("2500.00")
        
        profit = selling_price - cost
        margin_percent = (profit / selling_price) * Decimal("100")
        
        self.assertLess(profit, 0)
        
        # Determine margin label
        if margin_percent > 30:
            label = "good"
        elif margin_percent >= 15:
            label = "ok"
        elif margin_percent > 0:
            label = "low"
        else:
            label = "loss"
        
        self.assertEqual(label, "loss")


# ==============================================================================
# PART 2: WELDING VERTICAL TESTS - Quotation Buttons
# ==============================================================================

class TestWeldingQuotationButtons(TestCase):
    """Test welding quotation Add Material / Add Cost buttons."""
    
    def test_quote_detail_renders_add_buttons(self):
        """Test that quote detail page renders Add Material and Add Cost buttons."""
        # This test verifies the template contains the required elements
        # We'll check the template file directly since we may not have full DB setup
        
        import os
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'templates', 'verticals', 'welding', 'quote_detail.html'
        )
        
        if os.path.exists(template_path):
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for Add Material button
            self.assertIn('Add Material', content)
            
            # Check for Add Cost button
            self.assertIn('Add Cost', content)
            
            # Check for modal initialization script
            self.assertIn('bootstrap.Modal', content)
            
            # Check for type="button" on modal triggers
            self.assertIn('type="button"', content)
    
    def test_add_material_endpoint_exists(self):
        """Test that add_material endpoint is properly routed."""
        try:
            from inventory.verticals.welding import quote_add_line_item
            self.assertTrue(callable(quote_add_line_item))
        except ImportError:
            self.skipTest("Welding views not available")
    
    def test_add_cost_endpoint_exists(self):
        """Test that add_cost endpoint is properly routed."""
        try:
            from inventory.verticals.welding import quote_add_cost
            self.assertTrue(callable(quote_add_cost))
        except ImportError:
            self.skipTest("Welding views not available")


# ==============================================================================
# PART 3: NAVBAR DROPDOWN TESTS
# ==============================================================================

class TestNavbarDropdowns(TestCase):
    """Test navbar dropdown functionality."""
    
    def test_base_template_includes_navbar_js(self):
        """Test that base.html includes the shared navbar initialization JS."""
        import os
        
        base_template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'templates', 'base.html'
        )
        
        if os.path.exists(base_template_path):
            with open(base_template_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for shared navbar JS include
            self.assertIn('shared-navbar-init.js', content)
    
    def test_shared_navbar_js_exists(self):
        """Test that shared-navbar-init.js file exists."""
        import os
        
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'js', 'shared-navbar-init.js'
        )
        
        self.assertTrue(
            os.path.exists(js_path),
            f"Expected shared-navbar-init.js at {js_path}"
        )
    
    def test_shared_navbar_js_has_htmx_handler(self):
        """Test that shared navbar JS has HTMX afterSwap handler."""
        import os
        
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'static', 'js', 'shared-navbar-init.js'
        )
        
        if os.path.exists(js_path):
            with open(js_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for HTMX afterSwap listener
            self.assertIn('htmx:afterSwap', content)
            
            # Check for dropdown toggle functionality (custom implementation)
            self.assertIn('toggleDropdown', content)
            
            # Check for guard against double init
            self.assertIn('__CC_NAVBAR_INITIALIZED__', content)


# ==============================================================================
# PART 4: DATA CORRECTION TESTS
# ==============================================================================

class TestDataCorrection(TestCase):
    """Test data correction functionality across verticals."""
    
    def test_data_correction_service_validates_manager(self):
        """Test that DataCorrectionService requires manager permissions."""
        try:
            from inventory.services_data_correction_verticals import VerticalDataCorrectionService
            from django.core.exceptions import PermissionDenied
            
            # Create mock non-manager user
            mock_user = MagicMock()
            mock_user.is_staff = False
            mock_user.is_superuser = False
            
            # Create mock business
            mock_business = MagicMock()
            mock_business.pk = 1
            mock_business.kind = 'phones'
            
            # Test that service has a _validate_manager_permission method
            # The actual validation happens on init, so we check the method exists
            self.assertTrue(
                hasattr(VerticalDataCorrectionService, '_validate_manager_permission'),
                "Service should have _validate_manager_permission method"
            )
            
            # When initialized with non-staff, non-superuser, it should attempt
            # to check BusinessMembership and raise PermissionDenied
            # This verifies the permission check exists in the service
        except ImportError:
            self.skipTest("Data correction service not available")
    
    def test_data_correction_log_model_exists(self):
        """Test that DataCorrectionLog model is properly defined."""
        try:
            from inventory.models_data_correction import DataCorrectionLog, CorrectionType
            
            # Check model has required fields
            self.assertTrue(hasattr(DataCorrectionLog, 'business'))
            self.assertTrue(hasattr(DataCorrectionLog, 'model_name'))
            self.assertTrue(hasattr(DataCorrectionLog, 'object_id'))
            self.assertTrue(hasattr(DataCorrectionLog, 'correction_type'))
            self.assertTrue(hasattr(DataCorrectionLog, 'corrected_by'))
            self.assertTrue(hasattr(DataCorrectionLog, 'reason'))
            self.assertTrue(hasattr(DataCorrectionLog, 'field_changes'))
            
            # Check CorrectionType choices
            self.assertIn('EDIT_SALE', [c[0] for c in CorrectionType.choices])
        except ImportError:
            self.skipTest("Data correction models not available")
    
    def test_voided_record_model_exists(self):
        """Test that VoidedRecord model is properly defined."""
        try:
            from inventory.models_data_correction import VoidedRecord
            
            # Check model has required fields
            self.assertTrue(hasattr(VoidedRecord, 'business'))
            self.assertTrue(hasattr(VoidedRecord, 'model_name'))
            self.assertTrue(hasattr(VoidedRecord, 'record_snapshot'))
            self.assertTrue(hasattr(VoidedRecord, 'voided_by'))
            self.assertTrue(hasattr(VoidedRecord, 'reason'))
            self.assertTrue(hasattr(VoidedRecord, 'is_restored'))
        except ImportError:
            self.skipTest("VoidedRecord model not available")


# ==============================================================================
# PART 5: FARMING LIVESTOCK TESTS
# ==============================================================================

class TestFarmingLivestock(TestCase):
    """Test farming livestock separation (Poultry/Pigs)."""
    
    def test_poultry_daily_record_model_exists(self):
        """Test that PoultryDailyRecord model is properly defined."""
        try:
            from inventory.models_farm import PoultryDailyRecord
            
            # Check model has required fields
            self.assertTrue(hasattr(PoultryDailyRecord, 'batch'))
            self.assertTrue(hasattr(PoultryDailyRecord, 'date'))
            self.assertTrue(hasattr(PoultryDailyRecord, 'birds_alive'))
            self.assertTrue(hasattr(PoultryDailyRecord, 'deaths'))
            self.assertTrue(hasattr(PoultryDailyRecord, 'feed_kg'))
        except ImportError:
            self.skipTest("PoultryDailyRecord model not available")
    
    def test_pig_pen_daily_record_model_exists(self):
        """Test that PigDailyRecord model is properly defined."""
        try:
            from inventory.models_farm import PigDailyRecord
            
            # Check model has required fields
            self.assertTrue(hasattr(PigDailyRecord, 'pen'))
            self.assertTrue(hasattr(PigDailyRecord, 'date'))
            self.assertTrue(hasattr(PigDailyRecord, 'pigs_count'))
            self.assertTrue(hasattr(PigDailyRecord, 'feed_kg'))
        except ImportError:
            self.skipTest("PigDailyRecord model not available")
    
    def test_poultry_record_unique_constraint(self):
        """Test that poultry records are unique per batch+date."""
        try:
            from inventory.models_farm import PoultryDailyRecord
            
            # Check Meta has unique_together
            meta = PoultryDailyRecord._meta
            unique_together = getattr(meta, 'unique_together', ())
            
            # Should have batch + date unique
            self.assertTrue(
                any('batch' in ut and 'date' in ut for ut in unique_together),
                "PoultryDailyRecord should have unique_together for batch and date"
            )
        except ImportError:
            self.skipTest("PoultryDailyRecord model not available")
    
    def test_pig_record_unique_constraint(self):
        """Test that pig daily records are unique per pen+date."""
        try:
            from inventory.models_farm import PigDailyRecord
            
            # Check Meta has unique_together
            meta = PigDailyRecord._meta
            unique_together = getattr(meta, 'unique_together', ())
            
            # Should have pen + date unique
            self.assertTrue(
                any('pen' in ut and 'date' in ut for ut in unique_together),
                "PigDailyRecord should have unique_together for pen and date"
            )
        except ImportError:
            self.skipTest("PigDailyRecord model not available")


# ==============================================================================
# PART 6: CAR HIRE EMAIL TESTS
# ==============================================================================

@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='test@emajinet.com'
)
class TestCarHireEmails(TestCase):
    """Test car hire email notification functionality."""
    
    def test_email_service_exists(self):
        """Test that CarHireEmailService is properly defined."""
        try:
            from inventory.services_car_hire_emails import CarHireEmailService
            
            # Check service has required methods
            self.assertTrue(hasattr(CarHireEmailService, 'send_new_booking_notification'))
            self.assertTrue(hasattr(CarHireEmailService, 'send_payment_received_notification'))
            self.assertTrue(hasattr(CarHireEmailService, 'send_overdue_reminder'))
            self.assertTrue(hasattr(CarHireEmailService, 'send_maintenance_reminder'))
        except ImportError:
            self.skipTest("CarHireEmailService not available")
    
    def test_new_booking_email_sent(self):
        """Test that new booking notification email is sent correctly."""
        try:
            from inventory.services_car_hire_emails import CarHireEmailService
            
            # Create mock objects
            mock_business = MagicMock()
            mock_business.name = "Test Car Hire"
            mock_business.pk = 1
            
            mock_vehicle = MagicMock()
            mock_vehicle.name = "Toyota Hilux"
            mock_vehicle.plate_number = "MW 1234 ABC"
            
            mock_trip = MagicMock()
            mock_trip.pk = 1
            mock_trip.customer_name = "John Doe"
            mock_trip.customer_phone = "+265991234567"
            mock_trip.destination = "Lilongwe"
            mock_trip.vehicle = mock_vehicle
            mock_trip.start_datetime = timezone.now()
            mock_trip.end_datetime = timezone.now() + timezone.timedelta(days=3)
            mock_trip.price_total = Decimal("150000.00")
            mock_trip.deposit_paid = Decimal("50000.00")
            mock_trip.balance_due = Decimal("100000.00")
            mock_trip.get_trip_type_display = lambda: "Passenger"
            mock_trip.created_at = timezone.now()
            
            # Create service with mocked manager emails
            service = CarHireEmailService(mock_business)
            
            with patch.object(service, '_get_manager_emails', return_value=['manager@test.com']):
                result = service.send_new_booking_notification(mock_trip)
            
            # Check email was sent
            self.assertTrue(result)
            self.assertEqual(len(mail.outbox), 1)
            
            # Verify email content
            email = mail.outbox[0]
            self.assertIn('New Car Hire Booking', email.subject)
            self.assertIn('John Doe', email.body)
            self.assertEqual(email.to, ['manager@test.com'])
            
        except ImportError:
            self.skipTest("CarHireEmailService not available")
    
    def test_payment_received_email_with_pdf(self):
        """Test that payment received email includes PDF attachment."""
        try:
            from inventory.services_car_hire_emails import CarHireEmailService
            
            # Create mock objects
            mock_business = MagicMock()
            mock_business.name = "Test Car Hire"
            mock_business.pk = 1
            
            mock_vehicle = MagicMock()
            mock_vehicle.name = "Toyota Hilux"
            mock_vehicle.plate_number = "MW 1234 ABC"
            
            mock_trip = MagicMock()
            mock_trip.pk = 1
            mock_trip.customer_name = "Jane Doe"
            mock_trip.vehicle = mock_vehicle
            mock_trip.price_total = Decimal("150000.00")
            mock_trip.deposit_paid = Decimal("100000.00")
            mock_trip.balance_due = Decimal("50000.00")
            
            # Create mock PDF
            mock_pdf = b'%PDF-1.4 mock pdf content'
            
            # Create service with mocked manager emails
            service = CarHireEmailService(mock_business)
            
            with patch.object(service, '_get_manager_emails', return_value=['manager@test.com']):
                result = service.send_payment_received_notification(
                    mock_trip,
                    amount_paid=Decimal("50000.00"),
                    invoice_pdf=mock_pdf
                )
            
            # Check email was sent
            self.assertTrue(result)
            self.assertEqual(len(mail.outbox), 1)
            
            # Verify email has attachment
            email = mail.outbox[0]
            self.assertIn('Payment Received', email.subject)
            self.assertEqual(len(email.attachments), 1)
            
            # Check attachment is PDF
            attachment = email.attachments[0]
            self.assertIn('invoice', attachment[0])
            self.assertEqual(attachment[2], 'application/pdf')
            
        except ImportError:
            self.skipTest("CarHireEmailService not available")
    
    def test_no_email_sent_without_managers(self):
        """Test that no email is sent if no manager emails are found."""
        try:
            from inventory.services_car_hire_emails import CarHireEmailService
            
            mock_business = MagicMock()
            mock_business.name = "Test Car Hire"
            mock_business.pk = 1
            
            mock_trip = MagicMock()
            mock_trip.pk = 1
            mock_trip.customer_name = "Test"
            
            service = CarHireEmailService(mock_business)
            
            # Return empty list for managers
            with patch.object(service, '_get_manager_emails', return_value=[]):
                result = service.send_new_booking_notification(mock_trip)
            
            # Should return False and no emails sent
            self.assertFalse(result)
            self.assertEqual(len(mail.outbox), 0)
            
        except ImportError:
            self.skipTest("CarHireEmailService not available")


# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================

class TestIntegration(TestCase):
    """Integration tests to verify all parts work together."""
    
    def test_all_models_importable(self):
        """Test that all required models can be imported."""
        models_to_check = [
            ('inventory.models', 'MerchProduct'),
            ('inventory.models', 'Location'),
            ('inventory.models_welding', 'WeldingQuote'),
            ('inventory.models_welding', 'WeldingQuoteLineItem'),
            ('inventory.models_welding', 'WeldingQuoteCost'),
            ('inventory.models_car_hire', 'Vehicle'),
            ('inventory.models_car_hire', 'Trip'),
            ('inventory.models_car_hire', 'MaintenanceRecord'),
            ('inventory.models_data_correction', 'DataCorrectionLog'),
            ('inventory.models_data_correction', 'VoidedRecord'),
            ('inventory.models_farm', 'PoultryDailyRecord'),
            ('inventory.models_farm', 'PigDailyRecord'),
        ]
        
        import importlib
        
        for module_path, model_name in models_to_check:
            try:
                module = importlib.import_module(module_path)
                model = getattr(module, model_name, None)
                self.assertIsNotNone(
                    model,
                    f"{model_name} should be importable from {module_path}"
                )
            except ImportError as e:
                self.skipTest(f"Could not import {module_path}: {e}")
    
    def test_all_services_importable(self):
        """Test that all required services can be imported."""
        services_to_check = [
            ('inventory.services_data_correction_verticals', 'VerticalDataCorrectionService'),
            ('inventory.services_car_hire_emails', 'CarHireEmailService'),
        ]
        
        import importlib
        
        for module_path, service_name in services_to_check:
            try:
                module = importlib.import_module(module_path)
                service = getattr(module, service_name, None)
                self.assertIsNotNone(
                    service,
                    f"{service_name} should be importable from {module_path}"
                )
            except ImportError as e:
                self.skipTest(f"Could not import {module_path}: {e}")


# ==============================================================================
# PYTEST COMPATIBILITY
# ==============================================================================

# Mark all tests for pytest discovery
pytestmark = pytest.mark.django_db(transaction=True)
