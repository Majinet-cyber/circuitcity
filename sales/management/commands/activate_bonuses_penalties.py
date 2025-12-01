# sales/management/commands/activate_bonuses_penalties.py
"""
Management command to activate bonus/penalty settings and compute them retroactively.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal

from sales.models import CommissionConfig, Sale, SaleCommission
from tenants.models import Business
from timelogs.models import AgentWorkLog
from wallet.models import WalletTransaction, TxnType, Ledger
from wallet.services import add_txn


class Command(BaseCommand):
    help = "Activate bonus/penalty settings for all businesses and compute retroactively"
    
    def add_arguments(self, parser):
        parser.add_argument(
            "--business-id",
            type=int,
            help="Only activate for a specific business ID",
        )
        parser.add_argument(
            "--enable-early-bonus",
            action="store_true",
            help="Enable early arrival bonuses (default: True)",
        )
        parser.add_argument(
            "--enable-late-penalty",
            action="store_true",
            help="Enable late arrival penalties",
        )
        parser.add_argument(
            "--early-bonus-amount",
            type=float,
            default=5000.00,
            help="Bonus amount per 30min early (default: 5000 MWK)",
        )
        parser.add_argument(
            "--late-penalty-amount",
            type=float,
            default=7000.00,
            help="Penalty amount per 30min late (default: 7000 MWK)",
        )
        parser.add_argument(
            "--retroactive",
            action="store_true",
            help="Compute bonuses/penalties for existing sales",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
    
    def handle(self, *args, **options):
        business_id = options.get("business_id")
        enable_early = options.get("enable_early_bonus", True)
        enable_late = options.get("enable_late_penalty", False)
        early_amount = Decimal(str(options["early_bonus_amount"]))
        late_amount = Decimal(str(options["late_penalty_amount"]))
        retroactive = options.get("retroactive", False)
        dry_run = options.get("dry_run", False)
        
        # Get businesses to process
        if business_id:
            businesses = Business.objects.filter(id=business_id)
        else:
            businesses = Business.objects.all()
        
        if not businesses.exists():
            self.stdout.write(self.style.WARNING("No businesses found"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"Processing {businesses.count()} business(es)..."))
        
        for business in businesses:
            self.stdout.write(f"\n{'=' * 60}")
            self.stdout.write(f"Business: {business.name} (ID: {business.id})")
            self.stdout.write(f"{'=' * 60}")
            
            # Get or create CommissionConfig
            config = CommissionConfig.get_active(business)
            if not config:
                if dry_run:
                    self.stdout.write(self.style.WARNING(f"  [DRY RUN] Would create CommissionConfig"))
                else:
                    config = CommissionConfig.objects.create(
                        business=business,
                        is_active=True,
                    )
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Created CommissionConfig"))
            else:
                self.stdout.write(f"  Found existing CommissionConfig (ID: {config.id})")
            
            # Update settings
            if not dry_run:
                config.early_bonus_per_30min = early_amount
                config.late_penalty_per_30min = late_amount
                config.early_bonus_enabled = enable_early
                config.lateness_penalties_enabled = enable_late
                config.save()
                
                self.stdout.write(self.style.SUCCESS(f"  ✓ Updated settings:"))
                self.stdout.write(f"     Early bonus: {enable_early} (MK {early_amount}/30min)")
                self.stdout.write(f"     Late penalty: {enable_late} (MK {late_amount}/30min)")
            else:
                self.stdout.write(self.style.WARNING(f"  [DRY RUN] Would update settings:"))
                self.stdout.write(f"     Early bonus: {enable_early} (MK {early_amount}/30min)")
                self.stdout.write(f"     Late penalty: {enable_late} (MK {late_amount}/30min)")
            
            # Retroactive computation
            if retroactive:
                self.stdout.write(f"\n  Processing existing sales...")
                
                # Find sales without commission records
                sales_without_commission = Sale.objects.filter(
                    location__business=business
                ).exclude(
                    pk__in=SaleCommission.objects.values_list("sale_id", flat=True)
                )
                
                count = sales_without_commission.count()
                self.stdout.write(f"  Found {count} sales without commission records")
                
                if count > 0:
                    created_commissions = 0
                    bonus_total = Decimal("0.00")
                    penalty_total = Decimal("0.00")
                    
                    for sale in sales_without_commission:
                        if dry_run:
                            # Just count what would happen
                            try:
                                work_log = AgentWorkLog.objects.get(
                                    agent=sale.agent,
                                    business=business,
                                    work_date=sale.sold_at,
                                )
                                early_blocks = work_log.early_bonus_blocks
                                late_blocks = work_log.late_penalty_blocks
                                
                                if enable_early and early_blocks > 0:
                                    bonus_total += early_amount * early_blocks
                                if enable_late and late_blocks > 0:
                                    penalty_total += late_amount * late_blocks
                            except AgentWorkLog.DoesNotExist:
                                pass
                        else:
                            # Actually create commission records
                            try:
                                commission = SaleCommission.create_for_sale(sale)
                                created_commissions += 1
                                bonus_total += commission.early_bonus
                                penalty_total += commission.late_penalty
                                
                                # Create wallet transactions
                                if commission.early_bonus > 0:
                                    add_txn(
                                        agent=sale.agent,
                                        amount=commission.early_bonus,
                                        type=TxnType.BONUS,
                                        note=f"Early arrival bonus (retroactive): {commission.early_blocks} × 30min",
                                        reference=f"BONUS-RETRO-SALE-{sale.pk}",
                                        effective_date=sale.sold_at,
                                        ledger=Ledger.AGENT,
                                    )
                                
                                if commission.late_penalty > 0:
                                    add_txn(
                                        agent=sale.agent,
                                        amount=-commission.late_penalty,
                                        type=TxnType.PENALTY,
                                        note=f"Late arrival penalty (retroactive): {commission.late_blocks} × 30min",
                                        reference=f"PENALTY-RETRO-SALE-{sale.pk}",
                                        effective_date=sale.sold_at,
                                        ledger=Ledger.AGENT,
                                    )
                            except Exception as e:
                                self.stdout.write(self.style.ERROR(f"    Error processing sale {sale.pk}: {e}"))
                    
                    if dry_run:
                        self.stdout.write(self.style.WARNING(f"  [DRY RUN] Would create {count} commission records"))
                        self.stdout.write(f"     Total bonuses: MK {bonus_total:,.2f}")
                        self.stdout.write(f"     Total penalties: MK {penalty_total:,.2f}")
                    else:
                        self.stdout.write(self.style.SUCCESS(f"  ✓ Created {created_commissions} commission records"))
                        self.stdout.write(f"     Total bonuses: MK {bonus_total:,.2f}")
                        self.stdout.write(f"     Total penalties: MK {penalty_total:,.2f}")
        
        self.stdout.write(f"\n{'=' * 60}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN COMPLETE - No changes made"))
        else:
            self.stdout.write(self.style.SUCCESS("ACTIVATION COMPLETE"))
        self.stdout.write(f"{'=' * 60}\n")

