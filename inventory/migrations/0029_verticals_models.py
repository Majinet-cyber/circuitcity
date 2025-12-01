# Generated migration for verticals models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.core.validators import MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0028_alter_merchproduct_kind'),
        ('tenants', '0001_initial'),  # Adjust if needed
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add new fields to MerchProduct
        migrations.AddField(
            model_name='merchproduct',
            name='category',
            field=models.CharField(blank=True, default='', help_text='Liquor category: beer, cider, spirits, wine, other', max_length=20),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='barman_shots_reserved',
            field=models.PositiveIntegerField(default=2, help_text='Shots reserved for bartender (typically 2)'),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='price_per_bottle',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Price for a full bottle', max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='price_per_shot',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Price per individual shot', max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='is_archived',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='merchproduct',
            name='archived_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='archived_merch_products', to=settings.AUTH_USER_MODEL),
        ),
        
        # ====== LIQUOR MODELS ======
        
        migrations.CreateModel(
            name='LiquorSale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('unit', models.CharField(choices=[('bottle', 'Bottle'), ('shot', 'Shot')], default='bottle', max_length=10)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(Decimal('0.01'))])),
                ('total_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('sale_type', models.CharField(choices=[('sale', 'Cash Sale'), ('credit', 'Credit Sale'), ('undecided', 'Undecided')], default='sale', max_length=10)),
                ('is_credit', models.BooleanField(db_index=True, default=False)),
                ('sold_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('notes', models.TextField(blank=True, default='')),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liquor_sales', to='tenants.business')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='liquor_sales', to='inventory.merchproduct')),
                ('sold_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='liquor_sales_made', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-sold_at'],
            },
        ),
        
        migrations.CreateModel(
            name='LiquorCredit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('customer_name', models.CharField(max_length=120)),
                ('customer_phone', models.CharField(blank=True, default='', max_length=20)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[MinValueValidator(Decimal('0.01'))])),
                ('amount_paid', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('status', models.CharField(choices=[('open', 'Open'), ('partial', 'Partially Paid'), ('settled', 'Settled'), ('cancelled', 'Cancelled')], db_index=True, default='open', max_length=10)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('settled_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, default='')),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liquor_credits', to='tenants.business')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='liquor_credits_created', to=settings.AUTH_USER_MODEL)),
                ('related_sale', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='credits', to='inventory.liquorsale')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        migrations.AddField(
            model_name='liquorsale',
            name='linked_credit',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sales', to='inventory.liquorcredit'),
        ),
        
        migrations.CreateModel(
            name='LiquorCreditPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[MinValueValidator(Decimal('0.01'))])),
                ('transaction_id', models.CharField(blank=True, default='', max_length=100)),
                ('proof_file', models.FileField(blank=True, null=True, upload_to='liquor/credit_proofs/')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=10)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_reason', models.TextField(blank=True, default='')),
                ('credit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='inventory.liquorcredit')),
                ('paid_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='liquor_payments_submitted', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='liquor_payments_reviewed', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        migrations.CreateModel(
            name='LiquorStockEditRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requested_changes', models.JSONField(default=dict, help_text='JSON of fields to change')),
                ('reason', models.TextField(blank=True, default='')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=10)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_reason', models.TextField(blank=True, default='')),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liquor_stock_requests', to='tenants.business')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liquor_stock_requests', to='inventory.merchproduct')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liquor_stock_requests_submitted', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='liquor_stock_requests_reviewed', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        migrations.CreateModel(
            name='LiquorExpense',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[MinValueValidator(Decimal('0.01'))])),
                ('description', models.CharField(max_length=255)),
                ('category', models.CharField(blank=True, default='', max_length=50)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liquor_expenses', to='tenants.business')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='liquor_expenses_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        migrations.CreateModel(
            name='LiquorWalletEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('description', models.CharField(max_length=255)),
                ('entry_type', models.CharField(choices=[('income', 'Income'), ('expense', 'Expense')], max_length=20)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='liquor_wallet_entries', to='tenants.business')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='liquor_wallet_entries_created', to=settings.AUTH_USER_MODEL)),
                ('related_payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='wallet_entries', to='inventory.liquorcreditpayment')),
                ('related_sale', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='wallet_entries', to='inventory.liquorsale')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        # ====== GYM MODELS ======
        
        migrations.CreateModel(
            name='GymMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('phone', models.CharField(blank=True, default='', max_length=20)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('is_archived', models.BooleanField(db_index=True, default=False)),
                ('joined_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('archived_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, default='')),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gym_members', to='tenants.business')),
                ('archived_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gym_members_archived', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-joined_at'],
            },
        ),
        
        migrations.CreateModel(
            name='GymPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(Decimal('0.01'))])),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('paid_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('notes', models.TextField(blank=True, default='')),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='inventory.gymmember')),
                ('paid_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gym_payments_collected', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-paid_at'],
            },
        ),
        
        migrations.CreateModel(
            name='GymMemberLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('created', 'Created'), ('updated', 'Updated'), ('deleted', 'Deleted'), ('archived', 'Archived'), ('restored', 'Restored')], max_length=10)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='inventory.gymmember')),
                ('performed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gym_member_logs_created', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        migrations.CreateModel(
            name='GymSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('support_phone', models.CharField(blank=True, default='', max_length=20)),
                ('support_email', models.EmailField(blank=True, default='', max_length=254)),
                ('default_membership_price', models.DecimalField(decimal_places=2, default=Decimal('50000.00'), max_digits=10)),
                ('arrears_message', models.TextField(default='Your membership is in arrears. Please contact us to renew.')),
                ('business', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='gym_settings', to='tenants.business')),
            ],
            options={
                'verbose_name': 'Gym Settings',
                'verbose_name_plural': 'Gym Settings',
            },
        ),
        
        migrations.CreateModel(
            name='GymWalletEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('description', models.CharField(max_length=255)),
                ('entry_type', models.CharField(choices=[('income', 'Income'), ('expense', 'Expense')], max_length=20)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gym_wallet_entries', to='tenants.business')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gym_wallet_entries_created', to=settings.AUTH_USER_MODEL)),
                ('related_payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='wallet_entries', to='inventory.gympayment')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        # ====== CLOTHING MODELS ======
        
        migrations.CreateModel(
            name='ClothingProductLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('created', 'Created'), ('updated', 'Updated'), ('archived', 'Archived'), ('restored', 'Restored')], max_length=10)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('performed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clothing_logs_created', to=settings.AUTH_USER_MODEL)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clothing_logs', to='inventory.merchproduct')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        
        migrations.CreateModel(
            name='ClothingSale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(Decimal('0.01'))])),
                ('total_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('sold_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('notes', models.TextField(blank=True, default='')),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clothing_sales', to='tenants.business')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='clothing_sales', to='inventory.merchproduct')),
                ('sold_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='clothing_sales_made', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-sold_at'],
            },
        ),
        
        # Add indexes
        migrations.AddIndex(
            model_name='liquorsale',
            index=models.Index(fields=['business', '-sold_at'], name='liquor_sale_biz_date_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorsale',
            index=models.Index(fields=['business', 'sale_type', '-sold_at'], name='liquor_sale_type_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorsale',
            index=models.Index(fields=['is_credit', '-sold_at'], name='liquor_sale_credit_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorcredit',
            index=models.Index(fields=['business', 'status', '-created_at'], name='liquor_credit_status_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorcredit',
            index=models.Index(fields=['customer_name'], name='liquor_credit_customer_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorcreditpayment',
            index=models.Index(fields=['status', '-created_at'], name='liquor_payment_status_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorcreditpayment',
            index=models.Index(fields=['credit', '-created_at'], name='liquor_payment_credit_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorstockeditrequest',
            index=models.Index(fields=['business', 'status', '-created_at'], name='liquor_stock_req_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorstockeditrequest',
            index=models.Index(fields=['product', '-created_at'], name='liquor_stock_prod_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorexpense',
            index=models.Index(fields=['business', '-created_at'], name='liquor_expense_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorwalletentry',
            index=models.Index(fields=['business', '-created_at'], name='liquor_wallet_idx'),
        ),
        migrations.AddIndex(
            model_name='liquorwalletentry',
            index=models.Index(fields=['entry_type', '-created_at'], name='liquor_wallet_type_idx'),
        ),
        migrations.AddIndex(
            model_name='gymmember',
            index=models.Index(fields=['business', 'is_active', 'is_archived'], name='gym_member_status_idx'),
        ),
        migrations.AddIndex(
            model_name='gymmember',
            index=models.Index(fields=['phone'], name='gym_member_phone_idx'),
        ),
        migrations.AddIndex(
            model_name='gympayment',
            index=models.Index(fields=['member', '-paid_at'], name='gym_payment_member_idx'),
        ),
        migrations.AddIndex(
            model_name='gympayment',
            index=models.Index(fields=['start_date', 'end_date'], name='gym_payment_dates_idx'),
        ),
        migrations.AddIndex(
            model_name='gymmemberlog',
            index=models.Index(fields=['member', '-created_at'], name='gym_log_member_idx'),
        ),
        migrations.AddIndex(
            model_name='gymmemberlog',
            index=models.Index(fields=['action', '-created_at'], name='gym_log_action_idx'),
        ),
        migrations.AddIndex(
            model_name='gymwalletentry',
            index=models.Index(fields=['business', '-created_at'], name='gym_wallet_idx'),
        ),
        migrations.AddIndex(
            model_name='gymwalletentry',
            index=models.Index(fields=['entry_type', '-created_at'], name='gym_wallet_type_idx'),
        ),
        migrations.AddIndex(
            model_name='clothingproductlog',
            index=models.Index(fields=['product', '-created_at'], name='clothing_log_prod_idx'),
        ),
        migrations.AddIndex(
            model_name='clothingproductlog',
            index=models.Index(fields=['action', '-created_at'], name='clothing_log_action_idx'),
        ),
        migrations.AddIndex(
            model_name='clothingsale',
            index=models.Index(fields=['business', '-sold_at'], name='clothing_sale_idx'),
        ),
        
        # Add unique constraint for gym member
        migrations.AddConstraint(
            model_name='gymmember',
            constraint=models.UniqueConstraint(fields=['business', 'phone'], name='unique_gym_member_phone'),
        ),
    ]

