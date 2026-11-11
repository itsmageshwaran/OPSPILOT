Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  OpsPilot - Resetting Demo to Clean Baseline" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan

# Reset through OpsPilot so the configured ShopFlow URL is used and the
# running SQLite database is cleared without deleting an open database file.
Write-Host "Resetting ShopFlow and OpsPilot through the running backend..." -ForegroundColor Yellow
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/reset" -Method Post -TimeoutSec 10
    Write-Host "   OpsPilot database: reset" -ForegroundColor Green
    Write-Host "   ShopFlow: $($res.shopflow_reset)" -ForegroundColor Green
} catch {
    Write-Host "   Reset failed: start the backend and try again. No database files were deleted." -ForegroundColor Red
    exit 1
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Demo Reset Complete! Ready for Clean Presentation" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
