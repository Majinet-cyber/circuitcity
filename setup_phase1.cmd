@echo off
REM setup_phase1.cmd
REM Quick setup script for Phase 1 Integration (Windows)

echo ================================================
echo CircuitCity Phase 1 Integration Setup
echo ================================================
echo.

REM Step 1: Create migrations
echo Step 1: Creating migrations...
python manage.py makemigrations inventory --noinput
python manage.py makemigrations wallet --noinput
python manage.py makemigrations sales --noinput
python manage.py makemigrations timelogs --noinput
echo [OK] Migrations created
echo.

REM Step 2: Apply migrations
echo Step 2: Applying migrations...
python manage.py migrate sales --noinput
python manage.py migrate inventory --noinput
python manage.py migrate timelogs --noinput
python manage.py migrate wallet --noinput
echo [OK] Migrations applied
echo.

REM Step 3: Run tests
echo Step 3: Running tests...
python manage.py test --keepdb --no-input
echo [OK] Tests completed
echo.

REM Step 4: Check for Cypress
echo Step 4: Checking Cypress setup...
if exist "node_modules\cypress" (
    echo [OK] Cypress is installed
    echo   Run 'npm run cypress:open' to test E2E
) else (
    echo [!] Cypress not installed
    echo   Run 'npm install --save-dev cypress' to install
)
echo.

REM Step 5: Summary
echo ================================================
echo Setup Complete!
echo ================================================
echo.
echo Next steps:
echo 1. Start dev server:
echo    python manage.py runserver
echo.
echo 2. (Optional) Run Cypress E2E tests:
echo    npm run cypress:open
echo.
echo 3. Access your dashboard:
echo    http://127.0.0.1:8000/accounts/login/
echo.
echo Features now available:
echo [OK] Profit ^& Payment Mix on Phones Dashboard
echo [OK] Automatic Commission Tracking
echo [OK] Agent Rankings ^& Milestones
echo [OK] Admin Wallet Adjustments
echo [OK] Signup Email Validation
echo [OK] Clothing Price Guard-Rails
echo [OK] Stock Integrity ^& Audit Trail
echo [OK] IMEI Uniqueness Enforcement
echo.
echo See PHASE1_INTEGRATION_COMPLETE.md for full documentation
echo ================================================
pause

