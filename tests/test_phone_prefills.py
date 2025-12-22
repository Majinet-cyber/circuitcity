# tests/test_phone_prefills.py
"""
Tests for phone catalog prefills from wholesale list.

Tests that:
- Tecno, Itel, Samsung, Redmi models from wholesale list are seeded
- Models show correct RAM/ROM specs
- Non-standard specs (32+2, 32+3) are handled appropriately
- Other brands remain unchanged
"""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model

from tenants.models import Business
from inventory.business_kinds import BusinessKind
from inventory.phone_catalog_seed import (
    seed_phone_catalog,
    get_catalog_for_business,
    get_models_for_brand,
    FLAGSHIP_PHONES
)
from inventory.models_phone_products import PhoneProductCatalog

User = get_user_model()


@pytest.mark.django_db
class TestWholesaleListPrefills(TestCase):
    """Test wholesale list models are included in prefills"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testowner',
            email='owner@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
    
    def test_flagship_phones_includes_wholesale_models(self):
        """FLAGSHIP_PHONES should include wholesale list models"""
        # Check Tecno models
        tecno_models = [p for p in FLAGSHIP_PHONES if p['brand'] == 'TECNO']
        tecno_names = [p['model'] for p in tecno_models]
        
        assert 'SPARK 40' in tecno_names
        assert 'SPARK 40 Pro' in tecno_names
        assert 'SPARK 40 Pro+' in tecno_names
        assert 'SPARK 30' in tecno_names
        assert 'CAMON 40' in tecno_names
        assert 'CAMON 40 Pro' in tecno_names
        assert 'POP 10' in tecno_names
        assert 'POP 10C' in tecno_names
        
        # Check Itel models
        itel_models = [p for p in FLAGSHIP_PHONES if p['brand'] == 'ITEL']
        itel_names = [p['model'] for p in itel_models]
        
        assert 'A100C' in itel_names
        assert 'P65C' in itel_names
        assert 'A90' in itel_names
        assert 'V40' in itel_names  # 64+4 variant (standard)
        
        # Check Samsung models
        samsung_models = [p for p in FLAGSHIP_PHONES if p['brand'] == 'SAMSUNG']
        samsung_names = [p['model'] for p in samsung_models]
        
        assert 'Galaxy A05' in samsung_names
        assert 'Galaxy A06' in samsung_names
        assert 'Galaxy A15' in samsung_names
        assert 'Galaxy A16' in samsung_names
        assert 'Galaxy A36' in samsung_names
        assert 'Galaxy A56' in samsung_names
        assert 'Galaxy M05' in samsung_names
        assert 'Galaxy F05' in samsung_names
        
        # Check Redmi models
        redmi_models = [p for p in FLAGSHIP_PHONES if p['brand'] == 'REDMI']
        redmi_names = [p['model'] for p in redmi_models]
        
        assert 'NOTE 14' in redmi_names
        assert '15C' in redmi_names
        assert 'A3' in redmi_names
        assert 'A3X' in redmi_names
        assert 'A4 5G' in redmi_names
        assert 'A5' in redmi_names
        assert 'PAD 2' in redmi_names
    
    def test_wholesale_models_have_correct_specs(self):
        """Wholesale models should have correct RAM/ROM specs"""
        # Tecno SPARK 40: 128+4
        spark40 = [p for p in FLAGSHIP_PHONES if p['brand'] == 'TECNO' and p['model'] == 'SPARK 40' and p['ram'] == 4]
        assert len(spark40) > 0
        assert spark40[0]['rom'] == 128
        
        # Tecno SPARK 40 Pro: 256+8
        spark40pro = [p for p in FLAGSHIP_PHONES if p['brand'] == 'TECNO' and p['model'] == 'SPARK 40 Pro']
        assert len(spark40pro) > 0
        assert spark40pro[0]['ram'] == 8
        assert spark40pro[0]['rom'] == 256
        
        # Itel A90: should have BOTH 64+3 and 128+3
        a90_variants = [p for p in FLAGSHIP_PHONES if p['brand'] == 'ITEL' and p['model'] == 'A90']
        assert len(a90_variants) >= 2
        roms = [p['rom'] for p in a90_variants]
        assert 64 in roms
        assert 128 in roms
        
        # Samsung A15: 128+4
        a15 = [p for p in FLAGSHIP_PHONES if p['brand'] == 'SAMSUNG' and p['model'] == 'Galaxy A15']
        assert len(a15) > 0
        assert a15[0]['ram'] == 4
        assert a15[0]['rom'] == 128
        
        # Redmi NOTE 14: 256+8
        note14 = [p for p in FLAGSHIP_PHONES if p['brand'] == 'REDMI' and p['model'] == 'NOTE 14']
        assert len(note14) > 0
        assert note14[0]['ram'] == 8
        assert note14[0]['rom'] == 256
    
    def test_seed_creates_wholesale_models(self):
        """Seeding should create wholesale models in database"""
        created_count = seed_phone_catalog(self.business, self.user)
        
        assert created_count > 0
        
        # Verify Tecno Spark 40 created
        spark40 = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand='TECNO',
            model_name='SPARK 40',
            ram_gb=4,
            rom_gb=128
        ).first()
        assert spark40 is not None
        
        # Verify Itel A100C created
        a100c = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand='ITEL',
            model_name='A100C',
            ram_gb=2,
            rom_gb=64
        ).first()
        assert a100c is not None
        
        # Verify Samsung A16 created
        a16 = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand='SAMSUNG',
            model_name='Galaxy A16',
            ram_gb=4,
            rom_gb=128
        ).first()
        assert a16 is not None
        
        # Verify Redmi A3X created
        a3x = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand='REDMI',
            model_name='A3X',
            ram_gb=4,
            rom_gb=128
        ).first()
        assert a3x is not None


@pytest.mark.django_db
class TestNonStandardSpecs(TestCase):
    """Test handling of non-standard specs (32+2, 32+3)"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testowner',
            email='owner@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
    
    def test_non_standard_specs_excluded_from_primary_list(self):
        """Non-standard specs (32GB ROM) should not be in primary FLAGSHIP_PHONES"""
        # Check that 32GB ROM models are excluded or marked appropriately
        all_roms = [p['rom'] for p in FLAGSHIP_PHONES]
        
        # Count 32GB entries - should be minimal or zero
        rom_32_count = all_roms.count(32)
        
        # Most models should be 64GB+
        rom_64_plus = [r for r in all_roms if r >= 64]
        assert len(rom_64_plus) > rom_32_count
    
    def test_can_create_custom_non_standard_spec(self):
        """Users should be able to create custom products with non-standard specs"""
        # This would be done via "Custom/Other spec" option in wizard
        custom_product = PhoneProductCatalog.objects.create(
            business=self.business,
            brand='ITEL',
            model_name='V40',
            ram_gb=2,
            rom_gb=32,  # Non-standard
            variant_label='2+32',
            is_active=True,
            created_by=self.user
        )
        
        assert custom_product.id is not None
        assert custom_product.ram_gb == 2
        assert custom_product.rom_gb == 32


@pytest.mark.django_db
class TestTecnoItelPrimaryModels(TestCase):
    """Test Tecno and Itel models show as primary suggestions"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testowner',
            email='owner@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
        
        # Seed catalog
        seed_phone_catalog(self.business, self.user)
    
    def test_tecno_models_show_primary_suggestions(self):
        """Tecno models should appear as primary suggestions"""
        tecno_catalog = get_models_for_brand(self.business, 'TECNO')
        
        model_names = [m['model_name'] for m in tecno_catalog]
        
        # Wholesale list models should be present
        assert 'SPARK 40' in model_names
        assert 'SPARK 30' in model_names
        assert 'POP 10' in model_names
        assert 'CAMON 40' in model_names
    
    def test_itel_models_show_primary_suggestions(self):
        """Itel models should appear as primary suggestions"""
        itel_catalog = get_models_for_brand(self.business, 'ITEL')
        
        model_names = [m['model_name'] for m in itel_catalog]
        
        # Wholesale list models should be present
        assert 'A90' in model_names
        assert 'A100C' in model_names
        assert 'P65C' in model_names
    
    def test_model_shows_available_specs(self):
        """Each model should show its available RAM/ROM variants"""
        # Get Tecno SPARK 30 (has 2 variants: 128+4 and 256+8)
        spark30_variants = PhoneProductCatalog.objects.filter(
            business=self.business,
            brand='TECNO',
            model_name='SPARK 30'
        )
        
        variants_count = spark30_variants.count()
        assert variants_count >= 2  # At least 2 variants
        
        # Should have different RAM/ROM combinations
        specs = [(v.ram_gb, v.rom_gb) for v in spark30_variants]
        assert (4, 128) in specs
        assert (8, 256) in specs


@pytest.mark.django_db
class TestOtherBrandsUnchanged(TestCase):
    """Test that other brands remain unchanged"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testowner',
            email='owner@test.com',
            password='testpass123'
        )
        self.business = Business.objects.create(
            name='Test Phone Shop',
            business_kind=BusinessKind.PHONES,
            created_by=self.user
        )
        
        # Seed catalog
        seed_phone_catalog(self.business, self.user)
    
    def test_iphone_models_unchanged(self):
        """iPhone models should remain as they were"""
        iphone_catalog = get_models_for_brand(self.business, 'IPHONE')
        
        model_names = [m['model_name'] for m in iphone_catalog]
        
        # Should still have iPhone 16 series
        assert any('iPhone 16' in name for name in model_names)
        assert any('iPhone 15' in name for name in model_names)
    
    def test_huawei_models_unchanged(self):
        """Huawei models should remain unchanged"""
        huawei_catalog = get_models_for_brand(self.business, 'HUAWEI')
        
        model_names = [m['model_name'] for m in huawei_catalog]
        
        # Should still have Pura/Mate series
        assert any('Pura' in name for name in model_names) or any('Mate' in name for name in model_names)
    
    def test_pixel_models_unchanged(self):
        """Google Pixel models should remain unchanged"""
        pixel_catalog = get_models_for_brand(self.business, 'GOOGLE PIXEL')
        
        model_names = [m['model_name'] for m in pixel_catalog]
        
        # Should still have Pixel series
        assert any('Pixel' in name for name in model_names)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

