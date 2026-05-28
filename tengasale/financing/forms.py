from django import forms

from .models import Customer, Device, FinancingContract, PaymentRecord, UnlockToken


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "full_name",
            "phone_number",
            "customer_id_number",
            "address",
            "next_of_kin_name",
            "next_of_kin_phone",
        ]


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = [
            "brand",
            "model",
            "imei_1",
            "imei_2",
            "serial_number",
            "purchase_cost",
            "selling_price",
            "status",
            "assigned_customer",
        ]


class FinancingContractForm(forms.ModelForm):
    class Meta:
        model = FinancingContract
        fields = [
            "customer",
            "device",
            "deposit_amount",
            "total_loan_amount",
            "monthly_payment_amount",
            "term_months",
            "start_date",
            "next_due_date",
            "lock_date",
            "status",
            "notes",
        ]


class PaymentRecordForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contract"].widget = forms.HiddenInput()
        self.fields["customer"].widget = forms.HiddenInput()

    class Meta:
        model = PaymentRecord
        fields = [
            "contract",
            "customer",
            "amount",
            "payment_method",
            "transaction_reference",
            "proof_upload",
        ]


class PaymentRejectForm(forms.ModelForm):
    class Meta:
        model = PaymentRecord
        fields = ["rejection_reason"]
        widgets = {"rejection_reason": forms.Textarea(attrs={"rows": 3})}


class UnlockPinForm(forms.Form):
    token = forms.CharField(max_length=20, label="Unlock PIN")


class UnlockTokenAdminForm(forms.ModelForm):
    class Meta:
        model = UnlockToken
        fields = "__all__"
