Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  OpsPilot - Emergency Port Release (8000, 8080, 5173)" -ForegroundColor Yellow
Write-Host "===================================================" -ForegroundColor Cyan
python "$PSScriptRoot\scripts\free_ports.py"
Write-Host "Ports freed successfully!" -ForegroundColor Green
