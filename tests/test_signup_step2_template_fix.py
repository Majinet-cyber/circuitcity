"""
Minimal test to verify signup wizard step 2 template renders without VariableDoesNotExist errors.

This regression test ensures the fix for business_name/business_kind template errors works.
"""
from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from circuitcity.accounts.forms import ManagerWizardStep2Form


class SignupStep2TemplateRegressionTest(TestCase):
    """Test that the template fix for form.errors access works"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_template_renders_with_unbound_form(self):
        """
        Test that template renders without errors when form is unbound.

        This is the core regression test for the VariableDoesNotExist bug.
        The bug occurred when accessing form.errors.business_name on an unbound form.
        """
        # Create an unbound form (no data)
        form = ManagerWizardStep2Form()

        # Simulate the template code that was causing errors
        template_code = """
        {% if form.business_name.errors %}
            <div class="error">{{ form.business_name.errors|striptags }}</div>
        {% endif %}
        <input name="business_name" value="{{ form.business_name.value|default:'' }}">

        {% if form.business_kind.errors %}
            <div class="error">{{ form.business_kind.errors|striptags }}</div>
        {% endif %}
        <select name="business_kind">
            <option value="" {% if not form.business_kind.value %}selected{% endif %}>---</option>
            <option value="phones" {% if form.business_kind.value == 'phones' %}selected{% endif %}>Phones</option>
        </select>
        """

        template = Template(template_code)
        context = Context({"form": form})

        # This should NOT raise VariableDoesNotExist
        try:
            rendered = template.render(context)
            # If we get here, the template rendered successfully
            self.assertIn('name="business_name"', rendered)
            self.assertIn('name="business_kind"', rendered)
            # Should not have error divs since form is unbound
            self.assertNotIn('class="error"', rendered)
        except Exception as e:
            self.fail(f"Template rendering failed with: {e}")

    def test_template_renders_with_bound_invalid_form(self):
        """
        Test that template renders correctly when form has validation errors.
        """
        # Create a bound form with invalid data
        form = ManagerWizardStep2Form(data={})
        self.assertFalse(form.is_valid())  # Should have errors

        # Template code
        template_code = """
        {% if form.business_name.errors %}
            <div class="error">{{ form.business_name.errors|striptags }}</div>
        {% endif %}
        {% if form.business_kind.errors %}
            <div class="error">{{ form.business_kind.errors|striptags }}</div>
        {% endif %}
        """

        template = Template(template_code)
        context = Context({"form": form})

        # Should render with error messages
        try:
            rendered = template.render(context)
            # Should have error divs since form is invalid
            self.assertIn('class="error"', rendered)
            # Should contain "required" error message
            self.assertIn("required", rendered.lower())
        except Exception as e:
            self.fail(f"Template rendering failed with: {e}")

    def test_template_renders_with_valid_form(self):
        """
        Test that template renders correctly when form is valid.
        """
        # Create a bound form with valid data
        form = ManagerWizardStep2Form(
            data={
                "business_name": "Test Store",
                "business_kind": "phones",
                "subdomain": "teststore",
            }
        )
        self.assertTrue(form.is_valid())

        # Template code
        template_code = """
        <input name="business_name" value="{{ form.business_name.value|default:'' }}">
        <select name="business_kind">
            <option value="phones" {% if form.business_kind.value == 'phones' %}selected{% endif %}>Phones</option>
        </select>
        """

        template = Template(template_code)
        context = Context({"form": form})

        # Should render with values
        try:
            rendered = template.render(context)
            self.assertIn('value="Test Store"', rendered)
            self.assertIn("selected", rendered)  # phones option should be selected
        except Exception as e:
            self.fail(f"Template rendering failed with: {e}")
