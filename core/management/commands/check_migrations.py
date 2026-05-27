# core/management/commands/check_migrations.py
"""
Management command to check if all migrations are applied.
Use this in CI/CD pipelines to ensure migrations are not missing.
"""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Check if all migrations are applied and no unapplied migrations exist"

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-pending",
            action="store_true",
            help="Exit with error code if there are pending migrations",
        )

    def handle(self, *args, **options):
        # Check for unapplied migrations
        out = StringIO()
        call_command("showmigrations", "--plan", stdout=out)
        output = out.getvalue()

        # Count unapplied migrations (lines starting with [ ])
        unapplied = [line for line in output.split("\n") if line.strip().startswith("[ ]")]

        if unapplied:
            self.stdout.write(self.style.WARNING(f"\n⚠️  Found {len(unapplied)} unapplied migration(s):"))
            for migration in unapplied:
                self.stdout.write(self.style.WARNING(f"  {migration}"))

            self.stdout.write(self.style.WARNING("\n💡 Run: python manage.py migrate\n"))

            if options["fail_on_pending"]:
                raise CommandError("Unapplied migrations found. Run 'python manage.py migrate'")
        else:
            self.stdout.write(self.style.SUCCESS("\n✅ All migrations are applied!\n"))

        # Check for migrations that need to be created
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
            self.stdout.write(self.style.SUCCESS("✅ No missing migrations detected\n"))
        except Exception:
            self.stdout.write(self.style.ERROR("\n❌ Missing migrations detected!"))
            self.stdout.write(self.style.ERROR("💡 Run: python manage.py makemigrations\n"))
            if options["fail_on_pending"]:
                raise CommandError("Missing migrations detected. Run 'python manage.py makemigrations'")
