# Generated migration for InventoryBarcode, ArchiveBatch, and Laptop models

from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0063_add_spec_label_to_merchproduct'),  # Latest migration
        ('tenants', '0001_initial'),  # Adjust to your actual tenants migration
        ('auth', '0012_alter_user_first_name_max_length'),  # Adjust to your actual auth migration
    ]

    operations = [
        # Create InventoryBarcode model
        migrations.CreateModel(
            name='InventoryBarcode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(db_index=True, help_text='Barcode value (EAN, UPC, QR, etc.)', max_length=100, validators=[django.core.validators.MinLengthValidator(3)])),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('is_archived', models.BooleanField(db_index=True, default=False, help_text='Set to True to archive this barcode without deleting')),
                ('archived_at', models.DateTimeField(blank=True, db_index=True, help_text='When this barcode was archived', null=True)),
                ('business', models.ForeignKey(db_index=True, help_text='Business this barcode belongs to', on_delete=django.db.models.deletion.CASCADE, related_name='inventory_barcodes', to='tenants.business')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_stock_barcodes', to='auth.user')),
                ('location', models.ForeignKey(blank=True, help_text='Location where this barcode is stored (optional)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='barcodes', to='inventory.location')),
                ('product', models.ForeignKey(blank=True, help_text='Product this barcode belongs to', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='stock_barcodes', to='inventory.merchproduct')),
                ('archived_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='archived_stock_barcodes', to='auth.user')),
            ],
            options={
                'verbose_name': 'Inventory Barcode',
                'verbose_name_plural': 'Inventory Barcodes',
                'ordering': ['-created_at'],
            },
        ),
        
        # Create ArchiveBatch model
        migrations.CreateModel(
            name='ArchiveBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('reason', models.TextField(blank=True, help_text='Optional reason for archiving')),
                ('counts_snapshot', models.JSONField(blank=True, default=dict, help_text='JSON snapshot of affected records: products, stock_items, barcodes, etc.', null=True)),
                ('business', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name='archive_batches', to='tenants.business')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_archive_batches', to='auth.user')),
                ('location', models.ForeignKey(blank=True, help_text='Location archived (null if entire business)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='archive_batches', to='inventory.location')),
            ],
            options={
                'verbose_name': 'Archive Batch',
                'verbose_name_plural': 'Archive Batches',
                'ordering': ['-created_at'],
            },
        ),
        
        # Create LaptopProduct model
        migrations.CreateModel(
            name='LaptopProduct',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('brand', models.CharField(choices=[('dell', 'Dell'), ('lenovo', 'Lenovo'), ('apple', 'Apple (MacBook)'), ('hp', 'HP'), ('acer', 'Acer'), ('asus', 'Asus'), ('toshiba', 'Toshiba'), ('samsung', 'Samsung'), ('other', 'Other')], db_index=True, max_length=50)),
                ('model_name', models.CharField(help_text="Model name (e.g., 'ThinkPad X1', 'MacBook Pro 13')", max_length=100)),
                ('ram', models.CharField(blank=True, help_text="RAM specification (e.g., '8GB', '16GB DDR4')", max_length=50)),
                ('storage', models.CharField(blank=True, help_text="Storage specification (e.g., '256GB SSD', '1TB HDD')", max_length=50)),
                ('battery_life', models.CharField(blank=True, help_text="Battery life (e.g., '8 hours', '12 hours')", max_length=50)),
                ('default_cost_price', models.DecimalField(blank=True, decimal_places=2, help_text='Default cost price for this model', max_digits=10, null=True)),
                ('default_selling_price', models.DecimalField(blank=True, decimal_places=2, help_text='Default selling price for this model', max_digits=10, null=True)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name='laptop_products', to='tenants.business')),
            ],
            options={
                'verbose_name': 'Laptop Product',
                'verbose_name_plural': 'Laptop Products',
                'ordering': ['brand', 'model_name'],
            },
        ),
        
        # Create LaptopSerial model
        migrations.CreateModel(
            name='LaptopSerial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('serial', models.CharField(db_index=True, help_text='Laptop serial number (any format, must be unique per business)', max_length=100, validators=[django.core.validators.MinLengthValidator(3)])),
                ('received_at', models.DateField(default=django.utils.timezone.localdate, help_text='Date laptop was received/stocked')),
                ('order_price', models.DecimalField(decimal_places=2, default=0, help_text='Cost price when purchased', max_digits=12)),
                ('selling_price', models.DecimalField(blank=True, decimal_places=2, help_text='Selling price (can override product default)', max_digits=12, null=True)),
                ('status', models.CharField(choices=[('IN_STOCK', 'In Stock'), ('SOLD', 'Sold')], db_index=True, default='IN_STOCK', max_length=10)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('archived_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('archived_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='archived_laptop_serials', to='auth.user')),
                ('business', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, related_name='laptop_serials', to='tenants.business')),
                ('location', models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.PROTECT, related_name='laptop_serials', to='inventory.location')),
                ('product', models.ForeignKey(help_text='Laptop product model', on_delete=django.db.models.deletion.PROTECT, related_name='serials', to='inventory.laptopproduct')),
            ],
            options={
                'verbose_name': 'Laptop Serial',
                'verbose_name_plural': 'Laptop Serials',
                'ordering': ['-created_at'],
            },
        ),
        
        # Add indexes for InventoryBarcode (using unique names to avoid conflicts)
        migrations.AddIndex(
            model_name='inventorybarcode',
            index=models.Index(fields=['business', 'code', 'is_archived'], name='invbarcode_biz_code_active'),
        ),
        migrations.AddIndex(
            model_name='inventorybarcode',
            index=models.Index(fields=['product', 'is_archived'], name='invbarcode_product_active'),
        ),
        migrations.AddIndex(
            model_name='inventorybarcode',
            index=models.Index(fields=['location', 'is_archived'], name='invbarcode_location_active'),
        ),
        
        # Add unique constraint for InventoryBarcode (using unique name)
        migrations.AddConstraint(
            model_name='inventorybarcode',
            constraint=models.UniqueConstraint(condition=models.Q(('is_archived', False)), fields=['business', 'code'], name='unique_invbarcode_per_business'),
        ),
        
        # Add indexes for ArchiveBatch
        migrations.AddIndex(
            model_name='archivebatch',
            index=models.Index(fields=['business', 'created_at'], name='archive_batch_biz_date'),
        ),
        
        # Add indexes for LaptopProduct
        migrations.AddIndex(
            model_name='laptopproduct',
            index=models.Index(fields=['business', 'brand'], name='laptop_biz_brand'),
        ),
        migrations.AddIndex(
            model_name='laptopproduct',
            index=models.Index(fields=['business', 'is_active'], name='laptop_biz_active'),
        ),
        
        # Add unique constraint for LaptopProduct
        migrations.AlterUniqueTogether(
            name='laptopproduct',
            unique_together={('business', 'brand', 'model_name', 'ram', 'storage')},
        ),
        
        # Add indexes for LaptopSerial
        migrations.AddIndex(
            model_name='laptopserial',
            index=models.Index(fields=['business', 'serial', 'is_active'], name='laptop_serial_biz_code'),
        ),
        migrations.AddIndex(
            model_name='laptopserial',
            index=models.Index(fields=['business', 'status', 'is_active'], name='laptop_serial_status'),
        ),
        migrations.AddIndex(
            model_name='laptopserial',
            index=models.Index(fields=['product', 'status'], name='laptop_serial_product'),
        ),
        
        # Add unique constraint for LaptopSerial
        migrations.AddConstraint(
            model_name='laptopserial',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=['business', 'serial'], name='unique_laptop_serial_per_business'),
        ),
    ]

