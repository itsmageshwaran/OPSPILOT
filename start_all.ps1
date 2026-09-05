Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  OpsPilot - Starting Complete Incident Command Center" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan

$root = $PSScriptRoot

Write-Host "1. Starting ShopFlow on port 8000..." -ForegroundColor Yellow
Start-Process wt -ArgumentList "-w 0 new-tab --title ShopFlow-8000 -d `"$root\shopflow-test`" pwsh -NoExit -Command `"python -m uvicorn services.api_gateway.main:app --port 8000 --host 127.0.0.1`"" -ErrorAction SilentlyContinue
if (-not $?) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd `"$root\shopflow-test`"; python -m uvicorn services.api_gateway.main:app --port 8000 --host 127.0.0.1"
}

Write-Host "2. Starting OpsPilot Backend on port 8080..." -ForegroundColor Yellow
Start-Process wt -ArgumentList "-w 0 new-tab --title OpsPilot-8080 -d `"$root\backend`" pwsh -NoExit -Command `"python -m uvicorn app.main:app --port 8080 --host 127.0.0.1`"" -ErrorAction SilentlyContinue
if (-not $?) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd `"$root\backend`"; python -m uvicorn app.main:app --port 8080 --host 127.0.0.1"
}

Write-Host "3. Starting OpsPilot Frontend on port 5173..." -ForegroundColor Yellow
Start-Process wt -ArgumentList "-w 0 new-tab --title OpsPilot-UI -d `"$root\frontend`" pwsh -NoExit -Command `"npm run dev`"" -ErrorAction SilentlyContinue
if (-not $?) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd `"$root\frontend`"; npm run dev"
}

Start-Sleep -Seconds 3
Write-Host "Opening OpsPilot Dashboard..." -ForegroundColor Green
Start-Process "http://localhost:5173"
