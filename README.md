# CircuitCity Clean

Django 5.x project for business management.

## Quick Start

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
```

### Migration Verification

Before deploying, always run:
```bash
python bin/check_migrations.py
```

### Deployment to Render

**IMPORTANT**: If deploying to an existing database with migrations already applied, read [MIGRATION_FIX_DEPLOY.md](MIGRATION_FIX_DEPLOY.md) first.

For fresh deployments:
```bash
python manage.py migrate --noinput
```

## Testing

```bash
# Run all tests
python manage.py test

# Run migration tests
python manage.py test tests.test_migrations
```

## Documentation

- [MIGRATION_FIX_DEPLOY.md](MIGRATION_FIX_DEPLOY.md) - Migration fix deployment guide (READ BEFORE DEPLOYING)

## Migration Tools

- `bin/fix_migration_rename.py` - One-time script for existing databases
- `bin/check_migrations.py` - Pre-deployment verification
- `python manage.py verify_migrations` - Django command for migration checks
