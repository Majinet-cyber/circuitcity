# Generated manually for marketplace models
from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import inventory.models_marketplace


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tenants', '0031_car_hire_models'),
        ('inventory', '1033_merge_20260206_1331'),
        ('inventory', '0119_add_barcode_unit_to_clothing_sale'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketplaceListing',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vertical', models.CharField(blank=True, db_index=True, default='', help_text='Business vertical (phones, gym, pharmacy, etc.)', max_length=20)),
                ('title', models.CharField(help_text='Product or service name', max_length=200)),
                ('description', models.TextField(blank=True, default='', help_text='Detailed description (optional)')),
                ('price', models.DecimalField(blank=True, decimal_places=2, help_text='Price in business currency (optional)', max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(0)])),
                ('media_file', models.FileField(blank=True, help_text='Product photo or video (max 10 MB)', null=True, upload_to=inventory.models_marketplace.marketplace_media_upload_path, validators=[inventory.models_marketplace.validate_marketplace_media_size, inventory.models_marketplace.validate_marketplace_media_type])),
                ('is_active', models.BooleanField(db_index=True, default=True, help_text='Only active listings appear on marketplace')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(help_text='Business that owns this listing', on_delete=django.db.models.deletion.CASCADE, related_name='marketplace_listings', to='tenants.business')),
                ('created_by', models.ForeignKey(blank=True, help_text='User who created this listing', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='marketplace_listings_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='MarketplaceEnquiry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(help_text="Enquirer's email (required)", max_length=254, validators=[django.core.validators.EmailValidator()])),
                ('phone', models.CharField(blank=True, default='', help_text="Enquirer's phone number (optional)", max_length=20)),
                ('name', models.CharField(blank=True, default='', help_text="Enquirer's name (optional)", max_length=200)),
                ('message', models.TextField(blank=True, default='', help_text='Enquiry message (optional)')),
                ('is_read', models.BooleanField(db_index=True, default=False, help_text='Whether manager has read this enquiry')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('read_at', models.DateTimeField(blank=True, help_text='When manager marked this as read', null=True)),
                ('business', models.ForeignKey(help_text='Business receiving this enquiry (denormalized for easy queries)', on_delete=django.db.models.deletion.CASCADE, related_name='marketplace_enquiries', to='tenants.business')),
                ('listing', models.ForeignKey(help_text='Listing this enquiry is about', on_delete=django.db.models.deletion.CASCADE, related_name='enquiries', to='inventory.marketplacelisting')),
            ],
            options={
                'verbose_name_plural': 'Marketplace enquiries',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='marketplacelisting',
            index=models.Index(fields=['business', 'is_active'], name='inventory_m_busines_e6b7e3_idx'),
        ),
        migrations.AddIndex(
            model_name='marketplacelisting',
            index=models.Index(fields=['vertical', 'is_active'], name='inventory_m_vertica_8f4c2a_idx'),
        ),
        migrations.AddIndex(
            model_name='marketplacelisting',
            index=models.Index(fields=['-created_at'], name='inventory_m_created_9d3f1b_idx'),
        ),
        migrations.AddIndex(
            model_name='marketplaceenquiry',
            index=models.Index(fields=['business', 'is_read'], name='inventory_m_busines_7a2d4e_idx'),
        ),
        migrations.AddIndex(
            model_name='marketplaceenquiry',
            index=models.Index(fields=['listing', '-created_at'], name='inventory_m_listing_5c8b9f_idx'),
        ),
        migrations.AddIndex(
            model_name='marketplaceenquiry',
            index=models.Index(fields=['-created_at'], name='inventory_m_created_1e6a7c_idx'),
        ),
    ]

