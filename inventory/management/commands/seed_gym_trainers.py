"""
Management command to seed default gym trainers for all gym businesses.
Creates 3 default trainers: Steve, Lester, Philip (editable in admin/UI).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models_verticals import GymTrainer
from tenants.models import Business


class Command(BaseCommand):
    help = "Seed default gym trainers (Steve, Lester, Philip) for all gym businesses"
    
    DEFAULT_TRAINERS = ["Steve", "Lester", "Philip"]
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--business-id',
            type=int,
            help='Seed trainers for a specific business ID only',
        )
    
    def handle(self, *args, **options):
        business_id = options.get('business_id')
        
        # Get gym businesses
        if business_id:
            businesses = Business.objects.filter(id=business_id, business_kind='gym')
        else:
            businesses = Business.objects.filter(business_kind='gym')
        
        if not businesses.exists():
            self.stdout.write(self.style.WARNING('No gym businesses found'))
            return
        
        total_created = 0
        total_existing = 0
        
        for business in businesses:
            self.stdout.write(f"\nProcessing business: {business.name} (ID: {business.id})")
            
            for trainer_name in self.DEFAULT_TRAINERS:
                trainer, created = GymTrainer.objects.get_or_create(
                    business=business,
                    name=trainer_name,
                    defaults={
                        'is_active': True,
                        'notes': 'Default trainer (auto-created)',
                    }
                )
                
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ Created trainer: {trainer_name}")
                    )
                    total_created += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  - Trainer already exists: {trainer_name}")
                    )
                    total_existing += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ Seeding complete! Created: {total_created}, Existing: {total_existing}"
            )
        )

