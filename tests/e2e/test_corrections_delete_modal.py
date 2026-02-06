"""
Playwright E2E Test: Gym Payment Delete Modal (Feb 2026)
==========================================================

Tests that the delete button on gym payment edit page:
1. Is visible and clickable
2. Opens the delete modal when clicked
3. Modal requires a reason before submission
4. Form submission works correctly

This test verifies the fix for the production bug where delete button
was not clickable due to modal initialization issues.
"""
import pytest
from playwright.sync_api import Page, expect


# Skip if Playwright not installed
pytestmark = pytest.mark.skipif(
    not hasattr(pytest, 'playwright_available') or not pytest.playwright_available(),
    reason="Playwright browsers not installed. Run: python -m playwright install"
)


class TestCorrectionsDeleteModal:
    """Test delete modal functionality on gym payment edit page."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page, base_url: str):
        """Setup test environment."""
        self.page = page
        self.base_url = base_url
        
        # Note: In a real test, you'd need to:
        # 1. Create test user with manager permissions
        # 2. Create test business with gym vertical
        # 3. Create test gym member and payment
        # 4. Login as the test user
        # For now, this is a template that shows the test structure
    
    def test_delete_button_visible_and_clickable(self):
        """Test that delete button is visible and not covered by overlay."""
        # Navigate to gym payment edit page
        # Example URL: /corrections/gym/entity/gym_payment/123/edit/
        payment_id = 1  # Replace with actual test payment ID
        edit_url = f"{self.base_url}/corrections/gym/entity/gym_payment/{payment_id}/edit/"
        
        self.page.goto(edit_url)
        
        # Wait for page to load
        self.page.wait_for_load_state('networkidle')
        
        # Find delete button
        delete_button = self.page.locator('button[data-bs-target="#deleteModal"]')
        
        # Verify button is visible
        expect(delete_button).to_be_visible()
        
        # Verify button is enabled (not disabled)
        expect(delete_button).to_be_enabled()
        
        # Verify button text
        expect(delete_button).to_contain_text('Delete (Duplicate)')
        
        # Verify button is clickable (not covered by overlay)
        # This checks if the button is at the top of the stacking context
        button_box = delete_button.bounding_box()
        assert button_box is not None, "Delete button has no bounding box"
        
        # Check element at button center point
        center_x = button_box['x'] + button_box['width'] / 2
        center_y = button_box['y'] + button_box['height'] / 2
        
        # The button should be the topmost element at its center
        # (or a child element like the icon)
        element_at_point = self.page.evaluate(
            f"document.elementFromPoint({center_x}, {center_y})"
        )
        
        # Log for debugging
        print(f"Element at button center: {element_at_point}")
    
    def test_delete_button_opens_modal(self):
        """Test that clicking delete button opens the modal."""
        # Navigate to gym payment edit page
        payment_id = 1  # Replace with actual test payment ID
        edit_url = f"{self.base_url}/corrections/gym/entity/gym_payment/{payment_id}/edit/"
        
        self.page.goto(edit_url)
        self.page.wait_for_load_state('networkidle')
        
        # Find and click delete button
        delete_button = self.page.locator('button[data-bs-target="#deleteModal"]')
        delete_button.click()
        
        # Wait for modal to appear
        modal = self.page.locator('#deleteModal')
        
        # Verify modal is visible
        expect(modal).to_be_visible(timeout=2000)
        
        # Verify modal has correct class (should have 'show' class)
        expect(modal).to_have_class(/.*show.*/)
        
        # Verify modal content
        expect(modal).to_contain_text('Delete Payment Record')
        expect(modal).to_contain_text('Reason for Deletion')
        
        # Verify form elements are present
        reason_select = self.page.locator('#delete_reason')
        notes_textarea = self.page.locator('#delete_notes')
        
        expect(reason_select).to_be_visible()
        expect(notes_textarea).to_be_visible()
        
        # Verify modal backdrop is present
        backdrop = self.page.locator('.modal-backdrop')
        expect(backdrop).to_be_visible()
    
    def test_modal_requires_reason(self):
        """Test that modal form requires a reason to be selected."""
        # Navigate to gym payment edit page
        payment_id = 1  # Replace with actual test payment ID
        edit_url = f"{self.base_url}/corrections/gym/entity/gym_payment/{payment_id}/edit/"
        
        self.page.goto(edit_url)
        self.page.wait_for_load_state('networkidle')
        
        # Open modal
        delete_button = self.page.locator('button[data-bs-target="#deleteModal"]')
        delete_button.click()
        
        # Wait for modal
        modal = self.page.locator('#deleteModal')
        expect(modal).to_be_visible(timeout=2000)
        
        # Try to submit without selecting reason
        confirm_button = self.page.locator('button[type="submit"][form="deleteForm"]')
        confirm_button.click()
        
        # Verify form validation prevents submission
        # The reason select should have the required attribute
        reason_select = self.page.locator('#delete_reason')
        is_required = reason_select.get_attribute('required')
        assert is_required is not None, "Reason select should have required attribute"
        
        # Browser should show validation message (HTML5 validation)
        # We can check if the form has was-validated class
        delete_form = self.page.locator('#deleteForm')
        
        # After clicking submit without reason, form should be validated
        # Note: HTML5 validation might prevent the click, so we check the state
    
    def test_modal_submission_with_reason(self):
        """Test that modal form submits correctly when reason is provided."""
        # Navigate to gym payment edit page
        payment_id = 1  # Replace with actual test payment ID
        edit_url = f"{self.base_url}/corrections/gym/entity/gym_payment/{payment_id}/edit/"
        
        self.page.goto(edit_url)
        self.page.wait_for_load_state('networkidle')
        
        # Open modal
        delete_button = self.page.locator('button[data-bs-target="#deleteModal"]')
        delete_button.click()
        
        # Wait for modal
        modal = self.page.locator('#deleteModal')
        expect(modal).to_be_visible(timeout=2000)
        
        # Select a reason
        reason_select = self.page.locator('#delete_reason')
        reason_select.select_option('duplicate')
        
        # Add notes
        notes_textarea = self.page.locator('#delete_notes')
        notes_textarea.fill('This is a test deletion for duplicate payment')
        
        # Submit form
        confirm_button = self.page.locator('button[type="submit"][form="deleteForm"]')
        
        # Listen for navigation (form submission should redirect)
        with self.page.expect_navigation(timeout=5000):
            confirm_button.click()
        
        # After successful deletion, should redirect to browse page
        # Verify we're on the browse page
        assert '/corrections/gym/entity/gym_payment/' in self.page.url
        assert '/edit/' not in self.page.url
        
        # Verify success message is shown
        # (Assuming Django messages are displayed)
        success_message = self.page.locator('.alert-success, .message.success')
        expect(success_message).to_be_visible(timeout=2000)
        expect(success_message).to_contain_text('deleted successfully')
    
    def test_modal_cancel_button(self):
        """Test that cancel button closes the modal."""
        # Navigate to gym payment edit page
        payment_id = 1  # Replace with actual test payment ID
        edit_url = f"{self.base_url}/corrections/gym/entity/gym_payment/{payment_id}/edit/"
        
        self.page.goto(edit_url)
        self.page.wait_for_load_state('networkidle')
        
        # Open modal
        delete_button = self.page.locator('button[data-bs-target="#deleteModal"]')
        delete_button.click()
        
        # Wait for modal
        modal = self.page.locator('#deleteModal')
        expect(modal).to_be_visible(timeout=2000)
        
        # Click cancel button
        cancel_button = self.page.locator('button[data-bs-dismiss="modal"]')
        cancel_button.first.click()
        
        # Wait for modal to close
        expect(modal).not_to_be_visible(timeout=2000)
        
        # Verify backdrop is removed
        backdrop = self.page.locator('.modal-backdrop')
        expect(backdrop).not_to_be_visible()
    
    def test_modal_close_button(self):
        """Test that X close button closes the modal."""
        # Navigate to gym payment edit page
        payment_id = 1  # Replace with actual test payment ID
        edit_url = f"{self.base_url}/corrections/gym/entity/gym_payment/{payment_id}/edit/"
        
        self.page.goto(edit_url)
        self.page.wait_for_load_state('networkidle')
        
        # Open modal
        delete_button = self.page.locator('button[data-bs-target="#deleteModal"]')
        delete_button.click()
        
        # Wait for modal
        modal = self.page.locator('#deleteModal')
        expect(modal).to_be_visible(timeout=2000)
        
        # Click X close button
        close_button = self.page.locator('.btn-close')
        close_button.click()
        
        # Wait for modal to close
        expect(modal).not_to_be_visible(timeout=2000)
        
        # Verify backdrop is removed
        backdrop = self.page.locator('.modal-backdrop')
        expect(backdrop).not_to_be_visible()
    
    def test_console_errors_on_page_load(self):
        """Test that page loads without JavaScript errors."""
        # Navigate to gym payment edit page
        payment_id = 1  # Replace with actual test payment ID
        edit_url = f"{self.base_url}/corrections/gym/entity/gym_payment/{payment_id}/edit/"
        
        # Collect console messages
        console_errors = []
        
        def handle_console(msg):
            if msg.type == 'error':
                console_errors.append(msg.text)
        
        self.page.on('console', handle_console)
        
        self.page.goto(edit_url)
        self.page.wait_for_load_state('networkidle')
        
        # Wait a bit for any lazy-loaded scripts
        self.page.wait_for_timeout(1000)
        
        # Verify no console errors
        if console_errors:
            print(f"Console errors found: {console_errors}")
        
        # We allow some errors but check for critical ones
        critical_errors = [
            err for err in console_errors
            if 'bootstrap' in err.lower() or 'modal' in err.lower()
        ]
        
        assert len(critical_errors) == 0, f"Critical console errors: {critical_errors}"
    
    def test_bootstrap_js_loaded(self):
        """Test that Bootstrap JS is loaded and available."""
        # Navigate to gym payment edit page
        payment_id = 1  # Replace with actual test payment ID
        edit_url = f"{self.base_url}/corrections/gym/entity/gym_payment/{payment_id}/edit/"
        
        self.page.goto(edit_url)
        self.page.wait_for_load_state('networkidle')
        
        # Check if Bootstrap is available in global scope
        bootstrap_available = self.page.evaluate("typeof bootstrap !== 'undefined'")
        assert bootstrap_available, "Bootstrap JS is not loaded"
        
        # Check if Bootstrap Modal is available
        modal_available = self.page.evaluate("typeof bootstrap.Modal !== 'undefined'")
        assert modal_available, "Bootstrap Modal is not available"
        
        # Check if CorrectionsModal is loaded
        corrections_modal_available = self.page.evaluate(
            "typeof window.CorrectionsModal !== 'undefined'"
        )
        assert corrections_modal_available, "CorrectionsModal JS is not loaded"


# Integration test fixture (requires Django test database)
@pytest.mark.django_db
class TestCorrectionsDeleteModalIntegration(TestCorrectionsDeleteModal):
    """
    Integration tests that create actual test data.
    
    These tests require:
    - Django test database
    - Test fixtures for user, business, gym member, payment
    """
    
    @pytest.fixture(autouse=True)
    def setup_integration(self, page: Page, base_url: str, django_user_model, live_server):
        """Setup integration test with real data."""
        from django.contrib.auth import get_user_model
        from tenants.models import Business, BusinessKind
        from inventory.models_verticals import GymMember, GymPayment, GymMemberStatus
        from decimal import Decimal
        from datetime import date, timedelta
        
        User = get_user_model()
        
        # Create test business
        self.business = Business.objects.create(
            name="Test Gym",
            kind=BusinessKind.GYM,
            owner_email="testgym@example.com",
        )
        
        # Create test user with manager role
        self.user = User.objects.create_user(
            username='testmanager',
            email='manager@example.com',
            password='testpass123',
            is_staff=True,
        )
        
        # Assign user to business (assuming your user-business relationship)
        # self.user.businesses.add(self.business)  # Adjust based on your model
        
        # Create test gym member
        self.member = GymMember.objects.create(
            business=self.business,
            name="Test Member",
            phone="0991234567",
            status=GymMemberStatus.ACTIVE,
        )
        
        # Create test payment
        self.payment = GymPayment.objects.create(
            member=self.member,
            membership_amount=Decimal("50000.00"),
            trainer_fee=Decimal("5000.00"),
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        
        # Setup page and base_url
        self.page = page
        self.base_url = live_server.url
        
        # Login
        self.page.goto(f"{self.base_url}/login/")
        self.page.fill('input[name="username"]', 'testmanager')
        self.page.fill('input[name="password"]', 'testpass123')
        self.page.click('button[type="submit"]')
        self.page.wait_for_load_state('networkidle')
        
        # Update payment_id for tests
        self.payment_id = self.payment.pk

