import base64
import binascii
import uuid

from django import forms
from django.core.files.base import ContentFile

from .models import Contract


class MerchantTermsForm(forms.Form):
    confirmed_terms = forms.BooleanField(
        required=True,
        error_messages={"required": "Confirm that the terms were explained to the customer."},
    )


class ContractSignatureForm(forms.ModelForm):
    signature_data = forms.CharField(required=False, widget=forms.HiddenInput)
    customer_terms_accepted = forms.BooleanField(
        required=True,
        error_messages={"required": "Customer must confirm the contract terms."},
    )

    class Meta:
        model = Contract
        fields = ["customer_terms_accepted"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.signature_file = None

    def clean(self):
        cleaned_data = super().clean()
        signature_data = (cleaned_data.get("signature_data") or "").strip()
        prefix = "data:image/png;base64,"

        if not signature_data:
            self.add_error("signature_data", "Save the customer contract signature before continuing.")
            return cleaned_data

        if not signature_data.startswith(prefix):
            self.add_error("signature_data", "Save a valid PNG signature before continuing.")
            return cleaned_data

        try:
            decoded = base64.b64decode(signature_data[len(prefix):], validate=True)
        except (binascii.Error, ValueError):
            self.add_error("signature_data", "Save a valid PNG signature before continuing.")
        else:
            self.signature_file = ContentFile(decoded, name=f"contract-signature-{uuid.uuid4().hex}.png")

        return cleaned_data


class ImeiForm(forms.ModelForm):
    imei_number = forms.CharField(
        required=True,
        min_length=15,
        max_length=15,
        widget=forms.TextInput(
            attrs={
                "maxlength": "15",
                "minlength": "15",
                "pattern": "[0-9]{15}",
                "inputmode": "numeric",
                "autocomplete": "off",
                "data-imei-input": "true",
            }
        ),
    )

    class Meta:
        model = Contract
        fields = ["imei_number"]

    def clean_imei_number(self):
        value = (self.cleaned_data.get("imei_number") or "").strip()
        if not value.isdigit() or len(value) != 15:
            raise forms.ValidationError("IMEI must be exactly 15 digits.")
        return value
