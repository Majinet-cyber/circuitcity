# scripts/test_critical.ps1
# Critical Reliability Gate Test Runner for Windows PowerShell
#
# Usage:
#   .\scripts\test_critical.ps1          # Run critical tests
#   .\scripts\test_critical.ps1 -Verbose # Run with verbose output
#   .\scripts\test_critical.ps1 -Fast    # Run with --reuse-db for speed
#
# Exit codes:
#   0 = All critical tests passed
#   1 = One or more critical tests failed

param(
    [switch]$Verbose,
    [switch]$Fast,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Critical Reliability Gate Test Runner

Usage:
    .\scripts\test_critical.ps1 [options]

Options:
    -Verbose    Show detailed test output
    -Fast       Use --reuse-db for faster execution
    -Help       Show this help message

Examples:
    .\scripts\test_critical.ps1
    .\scripts\test_critical.ps1 -Verbose
    .\scripts\test_critical.ps1 -Fast -Verbose
"@
    exit 0
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  CRITICAL RELIABILITY GATE" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Running critical tests..." -ForegroundColor Yellow
Write-Host "These tests must ALL pass to deploy." -ForegroundColor Yellow
Write-Host ""

# Build pytest command
$pytestArgs = @("-m", "critical", "--maxfail=1")

if ($Verbose) {
    $pytestArgs += @("-v", "--tb=short")
} else {
    $pytestArgs += @("-q")
}

if ($Fast) {
    # Try to use reuse-db if available
    $pytestArgs += @("--reuse-db")
}

# Run pytest
$startTime = Get-Date
python -m pytest $pytestArgs
$exitCode = $LASTEXITCODE
$endTime = Get-Date
$duration = $endTime - $startTime

Write-Host ""
Write-Host "--------------------------------------" -ForegroundColor Gray

if ($exitCode -eq 0) {
    Write-Host "✓ ALL CRITICAL TESTS PASSED" -ForegroundColor Green
    Write-Host "  Duration: $($duration.TotalSeconds.ToString('F1')) seconds" -ForegroundColor Gray
    Write-Host "  Safe to deploy!" -ForegroundColor Green
} else {
    Write-Host "✗ CRITICAL TESTS FAILED" -ForegroundColor Red
    Write-Host "  Duration: $($duration.TotalSeconds.ToString('F1')) seconds" -ForegroundColor Gray
    Write-Host "  DO NOT DEPLOY until fixed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "To debug, run with -Verbose flag:" -ForegroundColor Yellow
    Write-Host "  .\scripts\test_critical.ps1 -Verbose" -ForegroundColor Yellow
}

Write-Host "--------------------------------------" -ForegroundColor Gray
Write-Host ""

exit $exitCode

