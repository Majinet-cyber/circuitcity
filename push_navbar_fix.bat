@echo off
cd /d "C:\Users\CHRIS PAUL MWALE\PycharmProjects\circuitcity_clean"

echo Adding files...
git add templates/base.html
git add tests/critical/test_13_navbar_dropdown_click_regression.py
git add tests/critical/test_14_navbar_dropdowns_production.py
git add NAVBAR_DROPDOWN_CLICK_FIX_JAN_2026.md
git add NAVBAR_DROPDOWN_PRODUCTION_FIX_JAN_2026.md

echo.
echo Committing...
git commit -m "fix(navbar): Restore dropdown click functionality (prod + local fix)" -m "" -m "CRITICAL FIX: Notifications and profile dropdowns now work in production" -m "" -m "ROOT CAUSE (PROD-ONLY):" -m "- CSS display: none !important blocked Bootstrap from showing dropdowns" -m "- JavaScript listened to show.bs.dropdown event which never fired" -m "- Created deadlock preventing clicks from opening dropdowns" -m "" -m "THE FIX (MULTI-LAYERED):" -m "1. Removed !important from dropdown hidden CSS" -m "2. Changed event listener from show.bs.dropdown to click (capture phase)" -m "3. Remove hidden attribute BEFORE Bootstrap processes click" -m "4. Verified service worker BUILD_ID injection" -m "5. Verified cache middleware sets no-store headers" -m "" -m "TESTING:" -m "- Added test_13_navbar_dropdown_click_regression.py (534 lines, 10 tests)" -m "- Added test_14_navbar_dropdowns_production.py (342 lines, 12 tests)" -m "- All existing tests pass (zero regressions)" -m "" -m "DELIVERABLES:" -m "- Dropdowns open on click (prod + local)" -m "- Works on billing pages" -m "- No hard refresh required" -m "- Works across all verticals" -m "- 22 comprehensive regression tests"

echo.
echo Pushing to GitHub...
git push origin mobile-layout-v1

echo.
echo Done! All changes pushed to GitHub.
pause

