"""
Management command: process_arrears_deductions

Finds active overdue/locked contracts and creates daily arrears deductions
for each missed day. Skips already-deducted dates. Idempotent.

Usage:
    python manage.py process_arrears_deductions
    python manage.py process_arrears_deductions --dry-run
    python manage.py process_arrears_deductions --days-back 7
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create arrears deductions for missed payment days on overdue/locked contracts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be created without writing to the database.",
        )
        parser.add_argument(
            "--days-back",
            type=int,
            default=30,
            help="How many past days to check for missed payments (default: 30).",
        )

    def handle(self, *args, **options):
        from portal.models import PaymentContract
        from commissions.services import create_daily_arrears_deduction

        dry_run = options["dry_run"]
        days_back = options["days_back"]
        today = timezone.localdate()

        contracts_checked = 0
        deductions_created = 0
        duplicates_skipped = 0
        errors = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no database writes."))

        overdue_contracts = PaymentContract.objects.filter(
            status__in=[
                PaymentContract.STATUS_OVERDUE,
                PaymentContract.STATUS_LOCKED,
            ]
        ).exclude(
            status__in=[
                PaymentContract.STATUS_COMPLETED,
                PaymentContract.STATUS_CANCELLED,
            ]
        ).prefetch_related("commission_ledger_entries")

        for contract in overdue_contracts:
            contracts_checked += 1

            underwriter = self._find_underwriter(contract)
            if underwriter is None:
                self.stdout.write(
                    self.style.WARNING(f"  Contract {contract.contract_number}: no underwriter found, skipping.")
                )
                continue

            already_deducted_dates = set(
                contract.commission_ledger_entries.filter(
                    entry_type="arrears_deduction",
                    missed_date__isnull=False,
                ).values_list("missed_date", flat=True)
            )

            start_date = contract.lock_date or contract.due_date or contract.start_date
            if start_date is None:
                continue

            check_date = max(start_date, today - timedelta(days=days_back))
            while check_date < today:
                if check_date not in already_deducted_dates:
                    if dry_run:
                        from commissions.services import calculate_arrears_deduction
                        amount = calculate_arrears_deduction(contract, missed_days=1)
                        self.stdout.write(
                            f"  [DRY RUN] Would create deduction -{amount} MWK for "
                            f"contract {contract.contract_number} on {check_date}"
                        )
                        deductions_created += 1
                    else:
                        try:
                            entry = create_daily_arrears_deduction(
                                contract=contract,
                                missed_date=check_date,
                                underwriter=underwriter,
                            )
                            if entry is not None:
                                deductions_created += 1
                            else:
                                duplicates_skipped += 1
                        except Exception as exc:
                            logger.error(
                                "Error creating arrears deduction for contract %s date %s: %s",
                                contract.pk, check_date, exc
                            )
                            errors += 1
                else:
                    duplicates_skipped += 1

                check_date += timedelta(days=1)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("─" * 50))
        self.stdout.write(self.style.SUCCESS("Arrears Deduction Summary"))
        self.stdout.write(self.style.SUCCESS("─" * 50))
        self.stdout.write(f"  Contracts checked   : {contracts_checked}")
        self.stdout.write(f"  Deductions created  : {deductions_created}")
        self.stdout.write(f"  Duplicates skipped  : {duplicates_skipped}")
        self.stdout.write(f"  Errors              : {errors}")
        if dry_run:
            self.stdout.write(self.style.WARNING("  (DRY RUN — nothing was written)"))

    def _find_underwriter(self, contract):
        """Find the underwriter assigned to a contract via the linked application."""
        try:
            financing_contract = getattr(contract, "financing_contract", None)
            if financing_contract:
                app = getattr(financing_contract, "application", None)
                if app:
                    return getattr(app, "claimed_by", None) or getattr(app, "reviewed_by", None)

            from applications.models import FinancingApplication
            app = FinancingApplication.objects.filter(
                status__in=["approved", "completed", "contract_complete"],
            ).filter(
                claimed_by__isnull=False,
            ).order_by("-reviewed_at").first()
            if app:
                return app.claimed_by or app.reviewed_by
        except Exception as exc:
            logger.warning("Could not find underwriter for contract %s: %s", contract.pk, exc)
        return None
