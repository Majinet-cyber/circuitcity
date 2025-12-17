@echo off
REM Verification script for Legacy Blocking + Mobile Overflow fixes (Windows)
REM Run this after deployment to ensure both fixes are working

echo ================================================
echo Legacy Blocking + Mobile Overflow Fix Verification
echo ================================================
echo.

set PASSED=0
set FAILED=0

echo Part A: Legacy Blocking Tests
echo ------------------------------

REM Test 1: Run Django tests for legacy blocking
echo Running Django legacy blocking tests...
python manage.py test inventory.tests.test_legacy_blocking --verbosity=0
if %ERRORLEVEL% == 0 (
    echo [32m✓ PASSED[0m
    set /a PASSED+=1
) else (
    echo [31m✗ FAILED[0m
    set /a FAILED+=1
)

echo.
echo Part B: Mobile Overflow Tests
echo -----------------------------

REM Test 2: Check if Cypress is available
where npx >nul 2>nul
if %ERRORLEVEL% == 0 (
    echo Running Cypress mobile overflow tests...
    npx cypress run --spec cypress/e2e/mobile_dashboard_overflow.cy.js --headless --quiet
    if %ERRORLEVEL% == 0 (
        echo [32m✓ PASSED[0m
        set /a PASSED+=1
    ) else (
        echo [31m✗ FAILED[0m
        set /a FAILED+=1
    )
) else (
    echo [33m⚠ Cypress not available (skip E2E tests)[0m
)

echo.
echo ================================================
echo Verification Summary
echo ================================================
echo [32mPassed: %PASSED%[0m
if %FAILED% GTR 0 (
    echo [31mFailed: %FAILED%[0m
    exit /b 1
) else (
    echo [32mAll tests passed! ✓[0m
    exit /b 0
)

