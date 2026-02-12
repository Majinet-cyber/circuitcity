# inventory/forms_liquor.py
"""
Django forms for Liquor wizard - proper server-side validation
"""
from django import forms
from decimal import Decimal
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind


class LiquorTypeSelectForm(forms.Form):
    """Step 1: Select liquor type"""
    LIQUOR_TYPES = [
        ('beer', 'Beer'),
        ('cider', 'Cider'),
        ('wine', 'Wine'),
        ('spirits', 'Spirits'),
        ('whisky', 'Whisky'),
    ]
    
    liquor_type = forms.ChoiceField(
        choices=LIQUOR_TYPES,
        required=True,
        error_messages={'required': 'Please select a category'}
    )


class LiquorProductForm(forms.Form):
    """Step 2: Product details"""
    product_name = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'e.g., Carlsberg Green',
            'autocomplete': 'off'
        }),
        error_messages={'required': 'Product name is required'}
    )
    
    cost_per_unit = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional',
            'step': '0.01'
        }),
        help_text='Cost price per bottle (optional)'
    )
    
    sell_per_unit = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Required',
            'step': '0.01'
        }),
        error_messages={'required': 'Selling price is required'}
    )
    
    # Beer/Cider-specific fields
    enable_pack = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    pack_size = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    sell_per_pack = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional discount price',
            'step': '0.01'
        })
    )
    
    # Wine-specific fields
    enable_glass = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    glasses_per_bottle = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    sell_per_glass = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional (auto-calculated if empty)',
            'step': '0.01'
        })
    )
    
    # Spirits/Whisky-specific fields
    enable_shot = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    shots_per_bottle = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    sell_per_shot = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional (auto-calculated if empty)',
            'step': '0.01'
        })
    )
    
    def clean_product_name(self):
        name = self.cleaned_data.get('product_name', '').strip()
        if not name:
            raise forms.ValidationError('Product name cannot be empty')
        return name
    
    def clean(self):
        cleaned_data = super().clean()
        sell_per_unit = cleaned_data.get('sell_per_unit')
        
        if not sell_per_unit or sell_per_unit <= 0:
            self.add_error('sell_per_unit', 'Selling price must be greater than 0')
        
        return cleaned_data


class LiquorStockInForm(forms.Form):
    """Form for adding stock to liquor products"""
    product = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput(),
        error_messages={'required': 'Please select a product'}
    )
    
    quantity = forms.IntegerField(
        required=True,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Number of bottles',
            'min': '1'
        }),
        error_messages={'required': 'Quantity is required', 'min_value': 'Quantity must be at least 1'}
    )
    
    cost_per_unit = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Cost per bottle',
            'step': '0.01'
        }),
        error_messages={'required': 'Cost price is required'}
    )
    
    date_received = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    notes = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes'
        })
    )


# ============================================================================
# PART B: Category-Aware Stock-In Forms (Effortless UX)
# ============================================================================


class BeerStockInForm(forms.Form):
    """
    B1) BEER stock-in form (crates-based).
    Users input: crates + cost_per_crate + optional loose bottles.
    System calculates everything else.
    """
    product_id = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput()
    )
    
    number_of_crates = forms.IntegerField(
        required=True,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Number of crates',
            'id': 'id_number_of_crates',
            'min': '0'
        }),
        error_messages={'required': 'Number of crates is required'}
    )
    
    cost_per_crate = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Cost per crate (MWK)',
            'id': 'id_cost_per_crate',
            'step': '0.01'
        }),
        error_messages={'required': 'Cost per crate is required'}
    )
    
    loose_bottles = forms.IntegerField(
        required=False,
        initial=0,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Loose bottles (optional)',
            'id': 'id_loose_bottles',
            'value': '0'
        })
    )
    
    date_received = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    notes = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes (supplier, invoice #, etc.)'
        })
    )


class CiderStockInForm(forms.Form):
    """
    B2) CIDER stock-in form (bottle-based).
    Users input: quantity_bottles + cost_per_bottle.
    System calculates total_cost.
    """
    product_id = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput()
    )
    
    quantity_bottles = forms.IntegerField(
        required=True,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Number of bottles',
            'id': 'id_quantity_bottles',
            'min': '1'
        }),
        error_messages={'required': 'Quantity is required'}
    )
    
    cost_per_bottle = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Cost per bottle (MWK)',
            'id': 'id_cost_per_bottle',
            'step': '0.01'
        }),
        error_messages={'required': 'Cost per bottle is required'}
    )
    
    date_received = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    notes = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes'
        })
    )


class WineStockInForm(forms.Form):
    """
    B3) WINE stock-in form (bottles → glasses).
    Users input: number_of_bottles + cost_per_bottle.
    System calculates: glasses (5 per bottle), cost_per_glass, total_cost.
    """
    product_id = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput()
    )
    
    number_of_bottles = forms.IntegerField(
        required=True,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Number of bottles',
            'id': 'id_number_of_bottles',
            'min': '1'
        }),
        error_messages={'required': 'Number of bottles is required'}
    )
    
    cost_per_bottle = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Cost per bottle (MWK)',
            'id': 'id_cost_per_bottle',
            'step': '0.01'
        }),
        error_messages={'required': 'Cost per bottle is required'}
    )
    
    date_received = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    notes = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes'
        })
    )


class SpiritsStockInForm(forms.Form):
    """
    B4) SPIRITS stock-in form (shots-based).
    Users input: quantity_of_shots_added + cost_per_shot + reserved_barman_shots.
    System calculates: sellable_shots, total_cost, equivalent_bottles.
    """
    product_id = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput()
    )
    
    quantity_of_shots_added = forms.IntegerField(
        required=True,
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Total shots added',
            'id': 'id_quantity_of_shots_added',
            'min': '1'
        }),
        error_messages={'required': 'Quantity of shots is required'}
    )
    
    cost_per_shot = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=True,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Cost per shot (MWK)',
            'id': 'id_cost_per_shot',
            'step': '0.01'
        }),
        error_messages={'required': 'Cost per shot is required'}
    )
    
    reserved_barman_shots = forms.IntegerField(
        required=False,
        initial=0,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Reserved for barman (optional)',
            'id': 'id_reserved_barman_shots',
            'value': '0'
        })
    )
    
    date_received = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        })
    )
    
    notes = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get('quantity_of_shots_added', 0)
        reserved = cleaned_data.get('reserved_barman_shots', 0)
        
        if reserved >= quantity:
            raise forms.ValidationError(
                'Reserved shots cannot exceed or equal total quantity.'
            )
        
        return cleaned_data


class WhiskyStockInForm(SpiritsStockInForm):
    """
    B5) WHISKY stock-in form (same as Spirits - shots-based).
    Inherits all fields and validation from SpiritsStockInForm.
    """
    pass
