import base64
from decimal import Decimal
from importlib import import_module
import shutil
import tempfile

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from deals.models import DeviceBrand, DeviceDeal

from .forms import CustomerDetailsForm, LocationForm, WorkForm
from .models import FinancingApplication


GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L"
    b"\x01\x00;"
)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\r\xefF\xb8\x00\x00\x00\x00IEND\xaeB`\x82"
)


def valid_signature_data():
    encoded = base64.b64encode(PNG_BYTES).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def valid_customer_data(**overrides):
    data = {
        "customer_name": "Jane Banda",
        "national_id": "RQXFVZC9",
        "customer_phone": "990870616",
        "occupation": "Trader",
        "income_band": "100,001-300,000",
        "exact_monthly_income": "250000",
    }
    data.update(overrides)
    return data


class ApplicationTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="merchant",
            password="test-pass-123",
        )
        self.client.login(username="merchant", password="test-pass-123")

    def create_application(self):
        return FinancingApplication.objects.create(created_by=self.user)

    def create_deal(self):
        brand = DeviceBrand.objects.create(name="TECNO")
        return DeviceDeal.objects.create(
            brand=brand,
            model_name="Pop 10C",
            specs="2+64",
            min_cash_price=Decimal("320000.00"),
            max_cash_price=Decimal("380000.00"),
            default_cash_price=Decimal("350000.00"),
            cash_price=Decimal("350000.00"),
            deposit_percent=Decimal("13.00"),
            loan_multiplier=Decimal("2.50"),
            term_months=12,
            total_12_month_price=Decimal("875000.00"),
        )


class CustomerValidationTests(TestCase):
    def assert_national_id_invalid(self, national_id):
        form = CustomerDetailsForm(data=valid_customer_data(national_id=national_id))

        self.assertFalse(form.is_valid())
        self.assertIn("national_id", form.errors)
        self.assertIn("National ID must be exactly 8 letters or numbers.", form.errors["national_id"])

    def assert_phone_invalid(self, phone):
        form = CustomerDetailsForm(data=valid_customer_data(customer_phone=phone))

        self.assertFalse(form.is_valid())
        self.assertIn("customer_phone", form.errors)
        self.assertIn("Phone number must be exactly 9 digits.", form.errors["customer_phone"])

    def test_blank_national_id_fails(self):
        self.assert_national_id_invalid("")

    def test_national_id_shorter_than_8_fails(self):
        self.assert_national_id_invalid("RQXFVZ")

    def test_national_id_longer_than_8_fails(self):
        self.assert_national_id_invalid("RQXFVZC99")

    def test_national_id_with_symbols_fails(self):
        self.assert_national_id_invalid("RQXF-ZC9")
        self.assert_national_id_invalid("@@@@@@@1")

    def test_national_id_with_spaces_fails(self):
        self.assert_national_id_invalid("RQXF ZC9")

    def test_national_id_with_8_digits_passes(self):
        form = CustomerDetailsForm(data=valid_customer_data(national_id="12345678"))

        self.assertTrue(form.is_valid(), form.errors)

    def test_national_id_with_8_letters_passes(self):
        form = CustomerDetailsForm(data=valid_customer_data(national_id="ABCDEFGH"))

        self.assertTrue(form.is_valid(), form.errors)

    def test_national_id_with_mixed_letters_and_digits_passes(self):
        form = CustomerDetailsForm(data=valid_customer_data(national_id="AB123CD4"))

        self.assertTrue(form.is_valid(), form.errors)

    def test_national_id_is_stored_uppercase(self):
        form = CustomerDetailsForm(data=valid_customer_data(national_id="wghjjju1"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["national_id"], "WGHJJJU1")

    def test_blank_phone_fails(self):
        self.assert_phone_invalid("")

    def test_phone_shorter_than_9_fails(self):
        self.assert_phone_invalid("99087061")

    def test_phone_longer_than_9_fails(self):
        self.assert_phone_invalid("99087061699")

    def test_phone_with_letters_fails(self):
        self.assert_phone_invalid("990abc870")

    def test_phone_with_symbols_fails(self):
        self.assert_phone_invalid("990-87061")

    def test_valid_9_digit_phone_passes(self):
        form = CustomerDetailsForm(data=valid_customer_data(customer_phone="990870616"))

        self.assertTrue(form.is_valid(), form.errors)

    def test_next_of_kin_phones_must_be_exactly_9_digits(self):
        location_form = LocationForm(data={"region": "Central", "district": "Lilongwe", "next_of_kin_1_phone": "123"})
        work_form = WorkForm(data={"next_of_kin_2_phone": "abcdefghi"})

        self.assertFalse(location_form.is_valid())
        self.assertFalse(work_form.is_valid())
        self.assertIn("next_of_kin_1_phone", location_form.errors)
        self.assertIn("next_of_kin_2_phone", work_form.errors)


class NextOfKinAndWorkFormTests(ApplicationTestCase):
    def location_data(self, **overrides):
        data = {
            "region": "Central",
            "district": "Lilongwe",
            "traditional_authority": "TA Chadza",
            "precise_location": "Area 25",
            "next_of_kin_1_name": "Mary Banda",
            "next_of_kin_1_phone": "991111111",
            "next_of_kin_1_relationship": "Family",
        }
        data.update(overrides)
        return data

    def work_data(self, **overrides):
        data = {
            "work_description": "Runs a grocery stall",
            "next_of_kin_2_name": "Peter Phiri",
            "next_of_kin_2_phone": "992222222",
            "next_of_kin_2_relationship": "Friend",
            "proof_of_income_type": "MoMo",
            "proof_contact_name": "Airtel Agent",
            "proof_contact_phone": "993333333",
            "proof_notes": "",
        }
        data.update(overrides)
        return data

    def test_location_page_contains_relationship_dropdown_choices(self):
        app = self.create_application()

        response = self.client.get(reverse("location_details", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="next_of_kin_1_relationship"')
        for choice in ["Family", "Friend", "Neighbour", "Other"]:
            self.assertContains(response, f'>{choice}</option>')

    def test_work_page_contains_relationship_dropdown_choices(self):
        app = self.create_application()

        response = self.client.get(reverse("work_details", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="next_of_kin_2_relationship"')
        for choice in ["Family", "Friend", "Neighbour", "Other"]:
            self.assertContains(response, f'>{choice}</option>')

    def test_relationship_fields_are_required(self):
        location_form = LocationForm()
        work_form = WorkForm()

        self.assertTrue(location_form.fields["next_of_kin_1_relationship"].required)
        self.assertTrue(work_form.fields["next_of_kin_2_relationship"].required)

    def test_next_of_kin_1_phone_same_as_customer_phone_fails(self):
        app = self.create_application()
        app.customer_phone = "990870616"
        form = LocationForm(data=self.location_data(next_of_kin_1_phone="990870616"), instance=app)

        self.assertFalse(form.is_valid())
        self.assertIn("Next of kin phone cannot be the same as customer phone.", form.errors["next_of_kin_1_phone"])

    def test_next_of_kin_2_phone_same_as_customer_phone_fails(self):
        app = self.create_application()
        app.customer_phone = "990870616"
        app.next_of_kin_1_phone = "991111111"
        form = WorkForm(data=self.work_data(next_of_kin_2_phone="990870616"), instance=app)

        self.assertFalse(form.is_valid())
        self.assertIn("Next of kin phone cannot be the same as customer phone.", form.errors["next_of_kin_2_phone"])

    def test_next_of_kin_2_phone_same_as_next_of_kin_1_phone_fails(self):
        app = self.create_application()
        app.customer_phone = "990870616"
        app.next_of_kin_1_phone = "991111111"
        form = WorkForm(data=self.work_data(next_of_kin_2_phone="991111111"), instance=app)

        self.assertFalse(form.is_valid())
        self.assertIn("Next of kin 2 phone cannot be the same as next of kin 1 phone.", form.errors["next_of_kin_2_phone"])

    def test_valid_next_of_kin_phone_passes(self):
        app = self.create_application()
        app.customer_phone = "990870616"
        form = LocationForm(data=self.location_data(next_of_kin_1_phone="991111111"), instance=app)

        self.assertTrue(form.is_valid(), form.errors)

    def test_next_of_kin_phone_with_letters_fails(self):
        app = self.create_application()
        form = LocationForm(data=self.location_data(next_of_kin_1_phone="991abc111"), instance=app)

        self.assertFalse(form.is_valid())
        self.assertIn("next_of_kin_1_phone", form.errors)

    def test_next_of_kin_phone_shorter_than_9_fails(self):
        app = self.create_application()
        form = LocationForm(data=self.location_data(next_of_kin_1_phone="99111111"), instance=app)

        self.assertFalse(form.is_valid())
        self.assertIn("next_of_kin_1_phone", form.errors)

    def test_next_of_kin_phone_longer_than_9_fails(self):
        app = self.create_application()
        form = LocationForm(data=self.location_data(next_of_kin_1_phone="9911111110"), instance=app)

        self.assertFalse(form.is_valid())
        self.assertIn("next_of_kin_1_phone", form.errors)

    def test_work_proof_required_fields(self):
        required_fields = [
            "work_description",
            "next_of_kin_2_name",
            "next_of_kin_2_phone",
            "next_of_kin_2_relationship",
            "proof_of_income_type",
            "proof_contact_name",
            "proof_contact_phone",
        ]

        for field in required_fields:
            app = self.create_application()
            app.customer_phone = "990870616"
            app.next_of_kin_1_phone = "991111111"
            form = WorkForm(data=self.work_data(**{field: ""}), instance=app)
            self.assertFalse(form.is_valid(), field)
            self.assertIn(field, form.errors)


class ApplicationUrlTests(ApplicationTestCase):
    def test_application_url_names_resolve(self):
        app = self.create_application()

        self.assertEqual(reverse("new_application"), "/applications/new/")
        self.assertEqual(reverse("edit_customer_details", args=[app.id]), f"/applications/{app.id}/customer/")
        self.assertEqual(reverse("choose_device", args=[app.id]), f"/applications/{app.id}/device/")
        self.assertEqual(reverse("kyc_capture", args=[app.id]), f"/applications/{app.id}/kyc/")
        self.assertEqual(reverse("location_details", args=[app.id]), f"/applications/{app.id}/location/")
        self.assertEqual(reverse("work_details", args=[app.id]), f"/applications/{app.id}/work/")
        self.assertEqual(reverse("signature", args=[app.id]), f"/applications/{app.id}/signature/")
        self.assertEqual(reverse("application_detail", args=[app.id]), f"/applications/{app.id}/detail/")
        self.assertEqual(reverse("active_applications"), "/applications/active/")
        self.assertEqual(reverse("completed_applications"), "/applications/completed/")
        self.assertEqual(reverse("rejected_applications"), "/applications/rejected/")

    def test_list_pages_return_200_for_logged_in_user(self):
        for name in ["active_applications", "completed_applications", "rejected_applications"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)


class ApplicationListTests(ApplicationTestCase):
    def test_submitted_unclaimed_application_shows_pending_review(self):
        app = self.create_application()
        app.customer_name = "Jane Banda"
        app.national_id = "RQXFVZC9"
        app.status = "submitted"
        app.save()

        response = self.client.get(reverse("active_applications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending Review")
        self.assertNotContains(response, "Submitted")
        self.assertContains(response, f'href="{reverse("application_detail", args=[app.id])}"')

    def test_claimed_application_shows_under_review(self):
        manager = get_user_model().objects.create_user(username="manager", password="test-pass-123", is_staff=True)
        app = self.create_application()
        app.customer_name = "Jane Banda"
        app.national_id = "RQXFVZC9"
        app.status = "under_review"
        app.claimed_by = manager
        app.save()

        response = self.client.get(reverse("active_applications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Under Review")
        self.assertContains(response, "Reviewer: manager")

    def test_active_applications_page_contains_clickable_continue_card(self):
        app = self.create_application()
        app.customer_name = "Jane Banda"
        app.national_id = "RQXFVZC9"
        app.status = "device_selection"
        app.save()

        response = self.client.get(reverse("active_applications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="application-card"')
        self.assertContains(response, f'href="{app.get_continue_url()}"')
        self.assertContains(response, "Jane Banda")
        self.assertContains(response, "ID: RQXFVZC9")
        self.assertContains(response, f"App: {app.application_number}")

    def test_completed_applications_page_contains_clickable_card(self):
        app = self.create_application()
        app.status = "completed"
        app.save()

        response = self.client.get(reverse("completed_applications"))

        self.assertContains(response, 'class="application-card"')
        self.assertContains(response, f'href="{app.get_continue_url()}"')
        self.assertEqual(app.get_continue_url(), reverse("application_detail", args=[app.id]))

    def test_needs_edit_application_page_contains_clickable_card(self):
        app = self.create_application()
        app.status = "correction_requested"
        app.save()

        response = self.client.get(reverse("active_applications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="application-card"')
        self.assertContains(response, "Needs Edit")
        self.assertNotContains(response, "Correction Requested")
        self.assertContains(response, f'href="{app.get_continue_url()}"')

    def test_rejected_applications_page_contains_clickable_card(self):
        app = self.create_application()
        app.status = "rejected"
        app.save()

        response = self.client.get(reverse("rejected_applications"))

        self.assertContains(response, 'class="application-card"')
        self.assertContains(response, f'href="{app.get_continue_url()}"')
        self.assertEqual(app.get_continue_url(), reverse("application_detail", args=[app.id]))

    def test_application_detail_uses_merchant_status_label(self):
        app = self.create_application()
        app.status = "correction_requested"
        app.save()

        response = self.client.get(reverse("application_detail", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs Edit")
        self.assertNotContains(response, "Correction Requested")

    def test_list_customer_and_detail_pages_contain_soft_back(self):
        app = self.create_application()

        urls = [
            reverse("active_applications"),
            reverse("completed_applications"),
            reverse("rejected_applications"),
            reverse("edit_customer_details", args=[app.id]),
            reverse("application_detail", args=[app.id]),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'class="soft-back"')


class ApplicationContinueUrlTests(ApplicationTestCase):
    def test_get_continue_url_returns_customer_page_for_started_and_customer_details(self):
        app = self.create_application()

        for status in ["started", "customer_details"]:
            app.status = status
            app.save(update_fields=["status"])
            self.assertEqual(app.get_continue_url(), reverse("edit_customer_details", args=[app.id]))

    def test_get_continue_url_returns_device_page_for_device_selection(self):
        app = self.create_application()
        app.status = "device_selection"
        app.save(update_fields=["status"])

        self.assertEqual(app.get_continue_url(), reverse("choose_device", args=[app.id]))

    def test_get_continue_url_returns_detail_page_for_terminal_statuses(self):
        app = self.create_application()

        for status in ["submitted", "rejected"]:
            app.status = status
            app.save(update_fields=["status"])
            self.assertEqual(app.get_continue_url(), reverse("application_detail", args=[app.id]))

    def test_approved_application_routes_to_contract_terms(self):
        app = self.create_application()
        app.status = "approved"
        app.save(update_fields=["status"])

        self.assertEqual(app.get_continue_url(), reverse("contract_terms", args=[app.id]))


class ApplicationDetailTests(ApplicationTestCase):
    def test_creator_can_access_application_detail(self):
        app = self.create_application()

        response = self.client.get(reverse("application_detail", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Application Detail")
        self.assertContains(response, 'class="soft-back"')

    def test_unrelated_user_gets_403_on_application_detail(self):
        app = self.create_application()
        get_user_model().objects.create_user(username="other", password="test-pass-123")
        self.client.login(username="other", password="test-pass-123")

        response = self.client.get(reverse("application_detail", args=[app.id]))

        self.assertEqual(response.status_code, 403)


class ApplicationFlowTests(ApplicationTestCase):
    def test_logged_in_user_can_start_new_application(self):
        response = self.client.get(reverse("new_application"))
        app = FinancingApplication.objects.get()

        self.assertRedirects(response, reverse("edit_customer_details", args=[app.id]))

    def test_customer_page_saves_valid_data_and_redirects_to_device_page(self):
        app = self.create_application()

        response = self.client.post(
            reverse("edit_customer_details", args=[app.id]),
            valid_customer_data(national_id="ab123cd4"),
        )

        app.refresh_from_db()
        self.assertRedirects(response, reverse("choose_device", args=[app.id]))
        self.assertEqual(app.national_id, "AB123CD4")
        self.assertEqual(app.customer_phone, "990870616")
        self.assertEqual(app.status, "customer_details")

    def test_after_valid_customer_details_user_lands_on_deal_selection(self):
        app = self.create_application()

        response = self.client.post(
            reverse("edit_customer_details", args=[app.id]),
            valid_customer_data(),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deal Selection")
        self.assertEqual(response.resolver_match.url_name, "choose_device")

    def test_invalid_national_id_does_not_proceed(self):
        app = self.create_application()

        response = self.client.post(
            reverse("edit_customer_details", args=[app.id]),
            valid_customer_data(national_id="RQXF-ZC9"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "National ID must be exactly 8 letters or numbers.")
        app.refresh_from_db()
        self.assertEqual(app.status, "started")

    def test_invalid_phone_number_does_not_proceed(self):
        app = self.create_application()

        response = self.client.post(
            reverse("edit_customer_details", args=[app.id]),
            valid_customer_data(customer_phone="990abc870"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Phone number must be exactly 9 digits.")
        app.refresh_from_db()
        self.assertEqual(app.status, "started")

    def test_customer_page_contains_input_locking_attributes_and_script(self):
        app = self.create_application()

        response = self.client.get(reverse("edit_customer_details", args=[app.id]))

        self.assertContains(response, 'maxlength="8"')
        self.assertContains(response, 'pattern="[A-Za-z0-9]{8}"')
        self.assertContains(response, 'maxlength="9"')
        self.assertContains(response, 'pattern="[0-9]{9}"')
        self.assertContains(response, "+265")
        self.assertContains(response, "data-national-id-input")
        self.assertContains(response, "data-phone-input")
        self.assertContains(response, "slice(0, limit)")

    def test_device_page_with_no_deals_does_not_crash(self):
        app = self.create_application()

        response = self.client.get(reverse("choose_device", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No deals available. Please ask management to add device deals.")

    def test_device_page_contains_seeded_brand_choices(self):
        app = self.create_application()
        call_command("seed_tengasale")

        response = self.client.get(reverse("choose_device", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TECNO")
        self.assertContains(response, "itel")
        self.assertContains(response, "Redmi")

    def test_device_page_contains_guided_flow_text_and_hidden_inputs(self):
        app = self.create_application()
        self.create_deal()

        response = self.client.get(reverse("choose_device", args=[app.id]))

        self.assertContains(response, "Choose brand")
        self.assertContains(response, "Choose model")
        self.assertContains(response, "Choose specs")
        self.assertContains(response, "Pay early, pay less")
        self.assertContains(response, "6 months")
        self.assertContains(response, "15% discount")
        self.assertContains(response, "3 months")
        self.assertContains(response, "25% discount")
        self.assertContains(response, 'name="deal_id"')
        self.assertContains(response, 'name="selected_cash_price"')

    def test_invalid_deal_id_post_returns_error(self):
        app = self.create_application()
        self.create_deal()

        response = self.client.post(
            reverse("choose_device", args=[app.id]),
            {"deal_id": "not-a-deal", "selected_cash_price": "360000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select an available device deal before continuing.")

    def test_valid_deal_selection_saves_calculated_values_and_redirects_to_kyc(self):
        app = self.create_application()
        deal = self.create_deal()

        response = self.client.post(
            reverse("choose_device", args=[app.id]),
            {"deal_id": deal.id, "selected_cash_price": "360000"},
        )

        app.refresh_from_db()
        self.assertRedirects(response, reverse("kyc_capture", args=[app.id]))
        self.assertEqual(app.deal, deal)
        self.assertEqual(app.selected_cash_price, Decimal("360000.00"))
        self.assertEqual(app.selected_deposit_percent, Decimal("13.00"))
        self.assertEqual(app.selected_loan_multiplier, Decimal("2.50"))
        self.assertEqual(app.calculated_total_loan, Decimal("900000.00"))
        self.assertEqual(app.calculated_deposit_amount, Decimal("117000.00"))
        self.assertEqual(app.calculated_monthly_payment, Decimal("75000.00"))
        self.assertEqual(app.calculated_daily_payment, Decimal("2500.00"))
        self.assertEqual(app.calculated_6_month_total, Decimal("765000.00"))
        self.assertEqual(app.calculated_6_month_monthly, Decimal("127500.00"))
        self.assertEqual(app.calculated_6_month_daily, Decimal("4250.00"))
        self.assertEqual(app.calculated_3_month_total, Decimal("675000.00"))
        self.assertEqual(app.calculated_3_month_monthly, Decimal("225000.00"))
        self.assertEqual(app.calculated_3_month_daily, Decimal("7500.00"))
        self.assertEqual(app.status, "device_selection")

    def test_selected_cash_price_below_min_returns_error(self):
        app = self.create_application()
        deal = self.create_deal()

        response = self.client.post(
            reverse("choose_device", args=[app.id]),
            {"deal_id": deal.id, "selected_cash_price": "319000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cash price must stay within the selected deal price range.")

    def test_selected_cash_price_above_max_returns_error(self):
        app = self.create_application()
        deal = self.create_deal()

        response = self.client.post(
            reverse("choose_device", args=[app.id]),
            {"deal_id": deal.id, "selected_cash_price": "381000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cash price must stay within the selected deal price range.")

    def test_kyc_location_and_work_pages_load(self):
        app = self.create_application()

        for name in ["kyc_capture", "location_details", "work_details"]:
            response = self.client.get(reverse(name, args=[app.id]))
            self.assertEqual(response.status_code, 200)

    def test_signature_page_requires_agreed_to_terms_before_submit(self):
        app = self.create_application()

        response = self.client.post(reverse("signature", args=[app.id]), {"signature_data": valid_signature_data()})

        self.assertEqual(response.status_code, 200)
        app.refresh_from_db()
        self.assertNotEqual(app.status, "submitted")

    def test_final_submit_sets_status_pending_review(self):
        app = self.create_application()

        response = self.client.post(
            reverse("signature", args=[app.id]),
            {"signature_data": valid_signature_data(), "agreed_to_terms": "on"},
        )

        app.refresh_from_db()
        self.assertRedirects(response, reverse("application_submitted", args=[app.id]))
        self.assertEqual(app.status, "pending_review")
        self.assertIsNotNone(app.submitted_at)


class SignaturePageTests(ApplicationTestCase):
    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def test_signature_page_contains_live_canvas_controls(self):
        app = self.create_application()

        response = self.client.get(reverse("signature", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<canvas")
        self.assertContains(response, "Undo")
        self.assertContains(response, "Clear / Cancel")
        self.assertContains(response, "Save Signature")
        self.assertNotContains(response, 'type="file"')

    def test_submit_without_signature_fails(self):
        app = self.create_application()

        response = self.client.post(reverse("signature", args=[app.id]), {"agreed_to_terms": "on"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save the customer signature before submitting.")
        app.refresh_from_db()
        self.assertNotEqual(app.status, "submitted")

    def test_submit_without_terms_fails(self):
        app = self.create_application()

        response = self.client.post(reverse("signature", args=[app.id]), {"signature_data": valid_signature_data()})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The customer must agree to the terms before submitting.")
        app.refresh_from_db()
        self.assertNotEqual(app.status, "submitted")

    def test_submit_with_valid_signature_and_terms_succeeds(self):
        app = self.create_application()

        response = self.client.post(
            reverse("signature", args=[app.id]),
            {"signature_data": valid_signature_data(), "agreed_to_terms": "on"},
        )

        app.refresh_from_db()
        self.assertRedirects(response, reverse("application_submitted", args=[app.id]))
        self.assertEqual(app.status, "pending_review")
        self.assertTrue(app.signature_image)
        self.assertTrue(app.agreed_to_terms)


class ApplicationDetailDataTests(ApplicationTestCase):
    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def test_detail_page_shows_next_of_kin_proof_and_signature_data(self):
        app = self.create_application()
        app.next_of_kin_1_name = "Mary Banda"
        app.next_of_kin_1_phone = "991111111"
        app.next_of_kin_1_relationship = "Family"
        app.next_of_kin_2_name = "Peter Phiri"
        app.next_of_kin_2_phone = "992222222"
        app.next_of_kin_2_relationship = "Friend"
        app.work_description = "Runs a grocery stall"
        app.proof_of_income_type = "MoMo"
        app.proof_contact_name = "Airtel Agent"
        app.proof_contact_phone = "993333333"
        app.agreed_to_terms = True
        app.signature_image.save("signature.png", ContentFile(PNG_BYTES), save=False)
        app.save()

        response = self.client.get(reverse("application_detail", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        for value in [
            "Mary Banda",
            "+265 991111111",
            "Family",
            "Peter Phiri",
            "+265 992222222",
            "Friend",
            "Runs a grocery stall",
            "MoMo",
            "Airtel Agent",
            "+265 993333333",
            "Customer signature",
            "Yes",
        ]:
            self.assertContains(response, value)


class KYCCaptureTests(ApplicationTestCase):
    def setUp(self):
        super().setUp()
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def image_upload(self, name):
        return SimpleUploadedFile(name, PNG_BYTES, content_type="image/png")

    def save_existing_images(self, app):
        app.customer_face_image.save("face.png", ContentFile(PNG_BYTES), save=False)
        app.id_front_image.save("front.png", ContentFile(PNG_BYTES), save=False)
        app.id_back_image.save("back.png", ContentFile(PNG_BYTES), save=False)
        app.save()

    def test_kyc_page_get_shows_live_capture_controls(self):
        app = self.create_application()

        response = self.client.get(reverse("kyc_capture", args=[app.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Capture Face")
        self.assertContains(response, "Capture ID Front")
        self.assertContains(response, "Capture ID Back")
        self.assertContains(response, 'class="soft-back"')
        self.assertContains(response, 'capture="user"')
        self.assertContains(response, 'capture="environment"', count=2)
        self.assertContains(response, 'class="kyc-file-input"')

    def test_kyc_post_without_images_stays_on_page_with_errors(self):
        app = self.create_application()

        response = self.client.post(reverse("kyc_capture", args=[app.id]), {})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer face image is required.")
        self.assertContains(response, "ID front image is required.")
        self.assertContains(response, "ID back image is required.")
        app.refresh_from_db()
        self.assertNotEqual(app.status, "kyc")

    def test_kyc_post_with_only_face_image_fails(self):
        app = self.create_application()

        response = self.client.post(
            reverse("kyc_capture", args=[app.id]),
            {"customer_face_image": self.image_upload("face.png")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ID front image is required.")
        self.assertContains(response, "ID back image is required.")

    def test_kyc_post_with_face_and_id_front_fails(self):
        app = self.create_application()

        response = self.client.post(
            reverse("kyc_capture", args=[app.id]),
            {
                "customer_face_image": self.image_upload("face.png"),
                "id_front_image": self.image_upload("front.png"),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ID back image is required.")

    def test_kyc_post_with_all_images_succeeds_and_redirects_to_location(self):
        app = self.create_application()

        response = self.client.post(
            reverse("kyc_capture", args=[app.id]),
            {
                "customer_face_image": self.image_upload("face.png"),
                "id_front_image": self.image_upload("front.png"),
                "id_back_image": self.image_upload("back.png"),
            },
        )

        app.refresh_from_db()
        self.assertRedirects(response, reverse("location_details", args=[app.id]))
        self.assertEqual(app.status, "kyc")
        self.assertTrue(app.customer_face_image)
        self.assertTrue(app.id_front_image)
        self.assertTrue(app.id_back_image)

    def test_existing_saved_images_show_previews_and_allow_continue(self):
        app = self.create_application()
        self.save_existing_images(app)

        response = self.client.get(reverse("kyc_capture", args=[app.id]))

        self.assertContains(response, "Customer Face preview")
        self.assertContains(response, "ID Front preview")
        self.assertContains(response, "ID Back preview")
        self.assertContains(response, 'data-existing="true"', count=3)
        self.assertNotContains(response, "data-next-button disabled")

        post_response = self.client.post(reverse("kyc_capture", args=[app.id]), {})
        self.assertRedirects(post_response, reverse("location_details", args=[app.id]))

    def test_recapture_controls_exist_and_new_image_replaces_saved_image(self):
        app = self.create_application()
        self.save_existing_images(app)
        original_face_name = app.customer_face_image.name

        response = self.client.get(reverse("kyc_capture", args=[app.id]))
        self.assertContains(response, "Recapture", count=3)

        post_response = self.client.post(
            reverse("kyc_capture", args=[app.id]),
            {"customer_face_image": self.image_upload("new-face.png")},
        )

        app.refresh_from_db()
        self.assertRedirects(post_response, reverse("location_details", args=[app.id]))
        self.assertNotEqual(app.customer_face_image.name, original_face_name)
        self.assertIn("kyc/faces/", app.customer_face_image.name)

    def test_another_user_cannot_access_or_modify_kyc_page(self):
        app = self.create_application()
        other_user = get_user_model().objects.create_user(
            username="other-merchant",
            password="test-pass-123",
        )
        self.client.login(username=other_user.username, password="test-pass-123")

        get_response = self.client.get(reverse("kyc_capture", args=[app.id]))
        post_response = self.client.post(
            reverse("kyc_capture", args=[app.id]),
            {
                "customer_face_image": self.image_upload("face.png"),
                "id_front_image": self.image_upload("front.png"),
                "id_back_image": self.image_upload("back.png"),
            },
        )

        app.refresh_from_db()
        self.assertEqual(get_response.status_code, 404)
        self.assertEqual(post_response.status_code, 404)
        self.assertFalse(app.customer_face_image)
        self.assertNotEqual(app.status, "kyc")


class ApplicationAdminImportTests(TestCase):
    def test_importing_applications_admin_does_not_crash(self):
        admin_module = import_module("applications.admin")

        self.assertIs(admin_module.FinancingApplication, FinancingApplication)

    def test_financing_application_is_registered_in_admin(self):
        self.assertIn(FinancingApplication, admin.site._registry)
