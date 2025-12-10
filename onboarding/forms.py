# onboarding/forms.py
from __future__ import annotations
from django import forms
from django.apps import apps
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils.text import slugify

User = get_user_model()

# Business form
Business = apps.get_model("tenants", "Business")

class BusinessForm(forms.ModelForm):
    """
    Business creation form for manager onboarding.
    Includes validation for:
    - Numeric-only names (rejected)
    - Duplicate store names (rejected)
    """
    class Meta:
        model = Business
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Your business name (e.g., Mo Touch Electronics)"
            })
        }
    
    def clean_name(self):
        """Validate business name with comprehensive checks."""
        name = (self.cleaned_data.get("name") or "").strip()
        
        if not name:
            raise ValidationError("Please provide a business/store name.")
        
        # Import validators
        try:
            from tenants.validators import validate_business_name, validate_business_name_not_numeric
        except ImportError:
            # Fallback validation if validators not available
            if name.replace(" ", "").isdigit():
                raise ValidationError(
                    "Store name cannot be only numbers. Please enter a proper business name."
                )
            return name
        
        # Check not numeric-only
        try:
            validate_business_name_not_numeric(name)
        except ValidationError as e:
            raise ValidationError(e.messages)
        
        # Check uniqueness (case-insensitive)
        if Business.objects.filter(name__iexact=name).exists():
            raise ValidationError(
                "That store name is already in use. Please pick another name or "
                "contact support if you believe this is an error."
            )
        
        # Apply basic business name validation
        try:
            validate_business_name(name)
        except ValidationError as e:
            raise ValidationError(e.messages)
        
        return name
    
    def clean(self):
        """Additional cleaning and slug generation."""
        cleaned = super().clean()
        name = cleaned.get("name")
        
        # Generate unique slug if model has slug field
        if name and hasattr(Business, "_meta"):
            field_names = {f.name for f in Business._meta.get_fields()}
            if "slug" in field_names:
                base_slug = slugify(name) or "shop"
                slug = base_slug
                counter = 1
                while Business.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                cleaned["slug"] = slug
        
        return cleaned


class ManagerSignupForm(forms.Form):
    """
    Manager signup form - Step 1: Email and password.
    Validates that the email is not already in use.
    """
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            "class": "form-control",
            "placeholder": "your@email.com",
            "autocomplete": "email"
        }),
        help_text="Your email address will be your username."
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Create a strong password",
            "autocomplete": "new-password"
        }),
        min_length=12,
        help_text="At least 12 characters with uppercase, lowercase, digit, and symbol."
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={
            "class": "form-control",
            "placeholder": "Confirm your password",
            "autocomplete": "new-password"
        }),
        min_length=12,
    )
    
    def clean_email(self):
        """
        Validate email is not already in use.
        One email = one manager account.
        """
        email = self.cleaned_data.get("email", "").strip().lower()
        
        if not email:
            raise ValidationError("Please provide an email address.")
        
        # Check if email already exists (case-insensitive)
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account with this email already exists. "
                "Please log in or reset your password instead of creating a new store."
            )
        
        return email
    
    def clean_password1(self):
        """Validate password using Django's password validators."""
        password = self.cleaned_data.get("password1", "")
        
        # Use Django's password validation
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(password)
        except ValidationError as e:
            raise ValidationError(e.messages)
        
        return password
    
    def clean(self):
        """Check password match."""
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Passwords do not match.")
        
        return cleaned

def make_inventory_item_form():
    """
    Create a dynamic ModelForm for inventory.InventoryItem with safe, common fields.
    """
    Model = apps.get_model("inventory", "InventoryItem")
    if not Model:
        return None
    wanted = ["name", "sku", "imei", "sale_price", "cost_price", "quantity", "location"]
    have = {f.name for f in Model._meta.get_fields()}
    fields = [f for f in wanted if f in have] or [next(iter(have - {"id"}))]  # at least 1 editable field

    Meta = type("Meta", (), {"model": Model, "fields": fields})
    Form = type("InventoryItemForm", (forms.ModelForm,), {"Meta": Meta})
    # add basic bootstrap widgets
    for f in fields:
        try:
            Form.base_fields[f].widget.attrs.update({"class": "form-control"})
        except Exception:
            pass
    return Form


