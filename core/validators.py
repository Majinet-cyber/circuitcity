"""
Reusable validators for input validation across the Circuit City SaaS.

These validators enforce data quality by rejecting invalid input patterns:
- Text-only fields (names, cities) should not contain digits
- Number-only fields (prices, quantities) should only contain digits
- Mixed fields (product names, addresses, SKUs) are intentionally NOT restricted

Usage:
    from core.validators import validate_no_digits, validate_digits_only
    
    # In forms:
    class MyForm(forms.Form):
        first_name = forms.CharField(validators=[validate_no_digits])
        quantity = forms.IntegerField(validators=[validate_digits_only])
"""
import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


# ============================================================================
# TEXT-ONLY VALIDATORS (no digits allowed)
# ============================================================================


def validate_no_digits(value):
    """
    Validate that a text field contains no digits.

    Use for: first_name, last_name, middle_name, city, district
    DO NOT use for: product names, business names, addresses, SKUs, emails, etc.

    Args:
        value: The value to validate

    Raises:
        ValidationError: If the value contains any digits (0-9)
    """
    if value and re.search(r"\d", str(value)):
        raise ValidationError(
            _("This field should not contain numbers. Please enter text only."), code="contains_digits"
        )


def validate_alphabetic_with_spaces(value):
    """
    Validate that a field contains only letters, spaces, hyphens, and apostrophes.
    More strict than validate_no_digits - useful for names.

    Use for: first_name, last_name (when you want to be strict)

    Args:
        value: The value to validate

    Raises:
        ValidationError: If the value contains anything other than letters, spaces, hyphens, apostrophes
    """
    if value and not re.match(r"^[A-Za-z\s\-']+$", str(value)):
        raise ValidationError(
            _("This field should only contain letters, spaces, hyphens, and apostrophes."), code="invalid_characters"
        )


# ============================================================================
# NUMBER-ONLY VALIDATORS
# ============================================================================


def validate_digits_only(value):
    """
    Validate that a field contains only digits.

    Use for: quantity fields, certain ID numbers
    DO NOT use for: phone numbers (may have +, spaces, dashes), prices (decimals)

    Args:
        value: The value to validate

    Raises:
        ValidationError: If the value contains non-digit characters
    """
    str_value = str(value).strip()
    if str_value and not str_value.isdigit():
        raise ValidationError(_("This field should contain only numbers (0-9)."), code="not_digits_only")


def validate_positive_decimal(value):
    """
    Validate that a value is a positive decimal number.

    Use for: prices, fees, commissions, amounts

    Args:
        value: The value to validate

    Raises:
        ValidationError: If the value is not a positive number
    """
    try:
        from decimal import Decimal, InvalidOperation

        decimal_value = Decimal(str(value))
        if decimal_value < 0:
            raise ValidationError(_("This value must be zero or greater."), code="negative_value")
    except (ValueError, InvalidOperation):
        raise ValidationError(_("Please enter a valid number."), code="invalid_number")


def validate_phone_number_format(value):
    """
    Validate phone number format (flexible).
    Allows: +, digits, spaces, dashes, parentheses

    Use for: phone number fields

    Args:
        value: The phone number to validate

    Raises:
        ValidationError: If the format is invalid
    """
    if not value:
        return

    # Remove common formatting characters
    cleaned = re.sub(r"[\s\-\(\)\+]", "", str(value))

    # Check if remaining characters are all digits
    if not cleaned.isdigit():
        raise ValidationError(
            _("Phone number should only contain digits, spaces, dashes, and optionally a + prefix."),
            code="invalid_phone_format",
        )

    # Check length (7-15 digits is reasonable for most phone numbers)
    if len(cleaned) < 7 or len(cleaned) > 15:
        raise ValidationError(_("Phone number should be between 7 and 15 digits."), code="invalid_phone_length")


def validate_imei_format(value):
    """
    Validate IMEI format (15 digits).

    Use for: IMEI fields in phone inventory

    Args:
        value: The IMEI to validate

    Raises:
        ValidationError: If the IMEI is not 15 digits
    """
    if not value:
        return

    str_value = str(value).strip()

    if not str_value.isdigit():
        raise ValidationError(_("IMEI must contain only digits."), code="imei_not_digits")

    if len(str_value) != 15:
        raise ValidationError(_("IMEI must be exactly 15 digits."), code="imei_wrong_length")


# ============================================================================
# PERCENTAGE VALIDATORS
# ============================================================================


def validate_percentage(value):
    """
    Validate that a value is a valid percentage (0-100).

    Use for: commission percentages, discount percentages

    Args:
        value: The percentage value to validate

    Raises:
        ValidationError: If the value is not between 0 and 100
    """
    try:
        from decimal import Decimal, InvalidOperation

        decimal_value = Decimal(str(value))
        if decimal_value < 0 or decimal_value > 100:
            raise ValidationError(_("Percentage must be between 0 and 100."), code="invalid_percentage")
    except (ValueError, InvalidOperation):
        raise ValidationError(_("Please enter a valid percentage."), code="invalid_percentage_format")


# ============================================================================
# QUANTITY VALIDATORS
# ============================================================================


def validate_positive_integer(value):
    """
    Validate that a value is a positive integer (>= 0).

    Use for: quantity, stock levels

    Args:
        value: The value to validate

    Raises:
        ValidationError: If the value is not a non-negative integer
    """
    try:
        int_value = int(value)
        if int_value < 0:
            raise ValidationError(_("Quantity must be zero or greater."), code="negative_quantity")
    except (ValueError, TypeError):
        raise ValidationError(_("Please enter a valid whole number."), code="invalid_integer")


# ============================================================================
# HELPER UTILITIES
# ============================================================================


def clean_phone_number(value):
    """
    Clean and normalize phone number for storage.
    Removes spaces, dashes, parentheses but keeps + prefix.

    Args:
        value: Raw phone number input

    Returns:
        Cleaned phone number string
    """
    if not value:
        return ""

    # Keep + prefix if present, remove other formatting
    cleaned = str(value).strip()
    if cleaned.startswith("+"):
        return "+" + re.sub(r"[^\d]", "", cleaned[1:])
    else:
        return re.sub(r"[^\d]", "", cleaned)


def clean_imei(value):
    """
    Clean and normalize IMEI for storage.
    Removes any non-digit characters.

    Args:
        value: Raw IMEI input

    Returns:
        Cleaned IMEI string (digits only)
    """
    if not value:
        return ""

    return re.sub(r"[^\d]", "", str(value))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Text validators
    "validate_no_digits",
    "validate_alphabetic_with_spaces",
    # Number validators
    "validate_digits_only",
    "validate_positive_decimal",
    "validate_phone_number_format",
    "validate_imei_format",
    "validate_percentage",
    "validate_positive_integer",
    # Utilities
    "clean_phone_number",
    "clean_imei",
]
