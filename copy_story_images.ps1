# ============================================================
# copy_story_images.ps1
# Run this script from the folder where your original
# story images live (with spaces/capitals in their names).
#
# Usage:
#   cd "C:\path\to\your\folder\with\the\images"
#   & "C:\Users\CHRIS PAUL MWALE\PycharmProjects\circuitcity_clean\copy_story_images.ps1"
#
# Or pass the source folder as argument:
#   & "...\copy_story_images.ps1" -SourceDir "C:\path\to\images"
# ============================================================

param(
    [string]$SourceDir = (Get-Location).Path
)

$Dest = "C:\Users\CHRIS PAUL MWALE\PycharmProjects\circuitcity_clean\static\landing\stories"

$Map = @{
    "gym Dashboard.png"            = "gym-dashboard.png"
    "gym dashboard 1.png"          = "gym-dashboard-1.png"
    "gym member public view.png"   = "gym-member-public-view.png"
    "gym member QR code.png"       = "gym-member-qr-code.png"
    "gym member.png"               = "gym-member.png"
    "GYM QR code.jpg"              = "gym-qr-code.jpg"
    "manual gym entry.jpg"         = "manual-gym-entry.jpg"
    "manual gym records.jpg"       = "manual-gym-records.jpg"
    "members payment status.png"   = "members-payment-status.png"
    "payment status.png"           = "payment-status.png"
    "phamarcy app sales.jpg"       = "pharmacy-app-sales.jpg"
    "phamarcy sales agent.jpg"     = "pharmacy-sales-agent.jpg"
    "Phamarcy stock.jpg"           = "pharmacy-stock.jpg"
    "training.jpg"                 = "gym-training.jpg"
    "Yohane Kajanga Gym owner.jpg" = "yohane-kajanga.jpg"
    "zaina.jpg"                    = "zaina.jpg"
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
$ok = 0; $miss = 0

foreach ($orig in $Map.Keys) {
    $src  = Join-Path $SourceDir $orig
    $dst  = Join-Path $Dest $Map[$orig]
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dst -Force
        Write-Host "  OK   $orig  ->  $($Map[$orig])" -ForegroundColor Green
        $ok++
    } else {
        Write-Host "  MISS $orig" -ForegroundColor Yellow
        $miss++
    }
}

Write-Host ""
Write-Host "Done: $ok copied, $miss not found." -ForegroundColor Cyan
Write-Host "Images are in: $Dest"
