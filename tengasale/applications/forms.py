from decimal import Decimal

from django import forms

from .models import FinancingApplication


INCOME_BANDS = [
    ("", "Select income band"),
    ("0-100,000", "0-100,000"),
    ("100,001-300,000", "100,001-300,000"),
    ("300,001-600,000", "300,001-600,000"),
    ("600,001+", "600,001+"),
]

REGIONS = [
    ("", "Select region"),
    ("Central", "Central"),
    ("Southern", "Southern"),
    ("Northern", "Northern"),
]

PROOF_TYPES = [
    ("", "Select proof type"),
    ("MoMo", "MoMo"),
    ("Bank", "Bank"),
    ("Till", "Till"),
    ("Contact Person", "Contact Person"),
]


def clean_exact_digits(value, length, field_label):
    value = (value or "").strip()
    if not value.isdigit() or len(value) != length:
        raise forms.ValidationError(f"{field_label} must be exactly {length} digits.")
    return value


class CustomerDetailsForm(forms.ModelForm):
    customer_name = forms.CharField(required=True, min_length=2, strip=True)
    national_id = forms.CharField(
        required=True,
        error_messages={"required": "National ID must be exactly 8 letters or numbers."},
        widget=forms.TextInput(
            attrs={
                "maxlength": "8",
                "minlength": "8",
                "pattern": "[A-Za-z0-9]{8}",
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
                "data-national-id-input": "true",
                "placeholder": "RQXFVZC9",
            }
        ),
    )
    customer_phone = forms.CharField(
        required=True,
        error_messages={"required": "Phone number must be exactly 9 digits."},
        widget=forms.TextInput(
            attrs={
                "maxlength": "9",
                "minlength": "9",
                "pattern": "[0-9]{9}",
                "inputmode": "numeric",
                "autocomplete": "tel",
                "data-phone-input": "true",
                "placeholder": "990870616",
            }
        ),
    )
    occupation = forms.CharField(required=True, min_length=2, strip=True)
    income_band = forms.ChoiceField(choices=INCOME_BANDS, required=True)
    exact_monthly_income = forms.DecimalField(required=True, min_value=Decimal("0.01"))

    class Meta:
        model = FinancingApplication
        fields = [
            "customer_name",
            "national_id",
            "customer_phone",
            "occupation",
            "income_band",
            "exact_monthly_income",
        ]

    def clean_national_id(self):
        value = (self.cleaned_data.get("national_id") or "").strip().upper()
        if len(value) != 8 or not value.isalnum():
            raise forms.ValidationError("National ID must be exactly 8 letters or numbers.")
        return value

    def clean_customer_phone(self):
        value = (self.cleaned_data.get("customer_phone") or "").strip()
        if not value.isdigit() or len(value) != 9:
            raise forms.ValidationError("Phone number must be exactly 9 digits.")
        return value


class KYCForm(forms.ModelForm):
    allowed_image_types = {"image/jpeg", "image/png", "image/webp"}

    class Meta:
        model = FinancingApplication
        fields = ["customer_face_image", "id_front_image", "id_back_image"]
        widgets = {
            "customer_face_image": forms.FileInput(
                attrs={
                    "accept": "image/*",
                    "capture": "user",
                    "class": "kyc-file-input",
                    "data-capture-input": "customer-face",
                }
            ),
            "id_front_image": forms.FileInput(
                attrs={
                    "accept": "image/*",
                    "capture": "environment",
                    "class": "kyc-file-input",
                    "data-capture-input": "id-front",
                }
            ),
            "id_back_image": forms.FileInput(
                attrs={
                    "accept": "image/*",
                    "capture": "environment",
                    "class": "kyc-file-input",
                    "data-capture-input": "id-back",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False

    def clean(self):
        cleaned_data = super().clean()
        labels = {
            "customer_face_image": "Customer face image",
            "id_front_image": "ID front image",
            "id_back_image": "ID back image",
        }

        for field_name, label in labels.items():
            uploaded_file = self.files.get(field_name)
            saved_file = getattr(self.instance, field_name, None)

            if not uploaded_file and not saved_file:
                self.add_error(field_name, f"{label} is required.")
                continue

            if uploaded_file and getattr(uploaded_file, "content_type", None) not in self.allowed_image_types:
                self.add_error(field_name, "Upload a JPEG, PNG, or WebP image.")

        return cleaned_data


KycForm = KYCForm


class LocationForm(forms.ModelForm):
    region = forms.ChoiceField(choices=REGIONS)
    district = forms.CharField(required=False, widget=forms.Select)
    next_of_kin_1_phone = forms.CharField(required=True)

    class Meta:
        model = FinancingApplication
        fields = [
            "region",
            "district",
            "traditional_authority",
            "precise_location",
            "map_screenshot",
            "next_of_kin_1_name",
            "next_of_kin_1_phone",
            "next_of_kin_1_relationship",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        district = self.data.get("district") or self.initial.get("district") or self.instance.district
        choices = [("", "Select district")]
        if district:
            choices.append((district, district))
        self.fields["district"].widget.choices = choices

    def clean_next_of_kin_1_phone(self):
        return clean_exact_digits(self.cleaned_data.get("next_of_kin_1_phone"), 9, "Next of kin 1 phone")


class WorkForm(forms.ModelForm):
    proof_of_income_type = forms.ChoiceField(choices=PROOF_TYPES, required=False)
    next_of_kin_2_phone = forms.CharField(required=True)

    class Meta:
        model = FinancingApplication
        fields = [
            "work_description",
            "next_of_kin_2_name",
            "next_of_kin_2_phone",
            "next_of_kin_2_relationship",
            "proof_of_income_type",
            "proof_contact_name",
            "proof_contact_phone",
            "proof_notes",
        ]

    def clean_next_of_kin_2_phone(self):
        return clean_exact_digits(self.cleaned_data.get("next_of_kin_2_phone"), 9, "Next of kin 2 phone")

    def clean_proof_contact_phone(self):
        value = (self.cleaned_data.get("proof_contact_phone") or "").strip()
        if not value:
            return value
        return clean_exact_digits(value, 9, "Proof contact phone")


class SignatureForm(forms.ModelForm):
    class Meta:
        model = FinancingApplication
        fields = ["signature_image", "agreed_to_terms"]

    def clean(self):
        cleaned_data = super().clean()
        signature = cleaned_data.get("signature_image") or self.instance.signature_image
        agreed = cleaned_data.get("agreed_to_terms")

        if not signature:
            self.add_error("signature_image", "Upload the customer signature before submitting.")
        if not agreed:
            self.add_error("agreed_to_terms", "The customer must agree to the terms before submitting.")

        return cleaned_data
