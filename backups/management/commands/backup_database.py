# backups/management/commands/backup_database.py
"""
Management command to create database backups.

Usage:
    python manage.py backup_database
    python manage.py backup_database --output /path/to/backup.sql
    python manage.py backup_database --upload-to-s3
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connections


class Command(BaseCommand):
    help = 'Create a database backup using pg_dump'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (default: backups/db/backup_YYYYMMDD_HHMMSS.sql)',
        )
        parser.add_argument(
            '--compress',
            action='store_true',
            help='Compress the backup with gzip',
        )
        parser.add_argument(
            '--upload-to-s3',
            action='store_true',
            help='Upload backup to S3 (requires AWS credentials)',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting database backup...'))

        # Get database configuration
        db_config = connections['default'].settings_dict
        
        if db_config['ENGINE'] != 'django.db.backends.postgresql':
            raise CommandError('This command only supports PostgreSQL databases')

        # Determine output path
        if options['output']:
            output_path = Path(options['output'])
        else:
            backup_dir = Path(settings.BASE_DIR) / 'backups' / 'db'
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'backup_{timestamp}.sql'
            if options['compress']:
                filename += '.gz'
            
            output_path = backup_dir / filename

        # Build pg_dump command
        cmd = [
            'pg_dump',
            '--host', db_config.get('HOST', 'localhost'),
            '--port', str(db_config.get('PORT', 5432)),
            '--username', db_config['USER'],
            '--dbname', db_config['NAME'],
            '--file', str(output_path),
            '--format', 'custom',  # Custom format for faster restore
            '--verbose',
        ]

        # Set password via environment variable
        env = os.environ.copy()
        if db_config.get('PASSWORD'):
            env['PGPASSWORD'] = db_config['PASSWORD']

        try:
            # Run pg_dump
            self.stdout.write(f'Running pg_dump to {output_path}...')
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )

            # Check if file was created
            if not output_path.exists():
                raise CommandError('Backup file was not created')

            file_size = output_path.stat().st_size
            file_size_mb = file_size / (1024 * 1024)

            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Backup created successfully: {output_path} ({file_size_mb:.2f} MB)'
                )
            )

            # Optional: Upload to S3
            if options['upload_to_s3']:
                self._upload_to_s3(output_path)

            # Log to database (optional)
            self._log_backup(output_path, file_size)

        except subprocess.CalledProcessError as e:
            raise CommandError(f'pg_dump failed: {e.stderr}')
        except Exception as e:
            raise CommandError(f'Backup failed: {str(e)}')

    def _upload_to_s3(self, backup_path: Path):
        """Upload backup to S3 (requires boto3)."""
        try:
            import boto3
            from botocore.exceptions import ClientError

            s3_bucket = getattr(settings, 'BACKUP_S3_BUCKET', None)
            if not s3_bucket:
                self.stdout.write(
                    self.style.WARNING('BACKUP_S3_BUCKET not configured, skipping S3 upload')
                )
                return

            s3_client = boto3.client('s3')
            s3_key = f'database_backups/{backup_path.name}'

            self.stdout.write(f'Uploading to S3: s3://{s3_bucket}/{s3_key}...')
            
            s3_client.upload_file(
                str(backup_path),
                s3_bucket,
                s3_key
            )

            self.stdout.write(
                self.style.SUCCESS(f'✓ Uploaded to S3: s3://{s3_bucket}/{s3_key}')
            )

        except ImportError:
            self.stdout.write(
                self.style.WARNING('boto3 not installed, skipping S3 upload')
            )
        except ClientError as e:
            self.stdout.write(
                self.style.ERROR(f'S3 upload failed: {e}')
            )

    def _log_backup(self, backup_path: Path, file_size: int):
        """Log backup to database for tracking."""
        try:
            # This is optional - you could create a DatabaseBackup model
            # to track infrastructure backups separately from per-business backups
            pass
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(f'Could not log backup: {e}')
            )

