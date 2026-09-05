$root = $PSScriptRoot

# 1. Augment PATH with standard Python and Node.js locations
$extraPaths = @(
    "$root\.venv\Scripts",
    "C:\Python313",
    "C:\Python312",
    "C:\Python311",
    "C:\Program Files\nodejs",
    "$env:LOCALAPPDATA\Programs\Python\Python313",
    "$env:LOCALAPPDATA\Programs\Python\Python312",
    "$env:LOCALAPPDATA\Programs\Python\Python311",
    "$env:APPDATA\npm"
)
foreach ($p in $extraPaths) {
    if ((Test-Path $p) -and ($env:PATH -notlike "*$p*")) {
        $env:PATH = "$p;$env:PATH"
    }
}

# 2. Resolve Python binary
$pythonExe = "python"
if (Test-Path "$root\.venv\Scripts\python.exe") {
    $pythonExe = "$root\.venv\Scripts\python.exe"
} elseif (Test-Path "C:\Python313\python.exe") {
    $pythonExe = "C:\Python313\python.exe"
}

# 3. Resolve NPM binary
$npmCmd = "npm"
if (Test-Path "C:\Program Files\nodejs\npm.cmd") {
    $npmCmd = "C:\Program Files\nodejs\npm.cmd"
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  OpsPilot - Starting Complete Incident Command Center" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "0. Releasing ports 8000, 8080, and 5173..." -ForegroundColor Yellow
& "$root\kill_ports.ps1"

Write-Host "1. Starting ShopFlow on port 8000..." -ForegroundColor Yellow
$shopflowCmd = "`$env:PATH = `"$env:PATH`"; cd `"$root\shopflow-test`"; & `"$pythonExe`" -m uvicorn services.api_gateway.main:app --port 8000 --host 127.0.0.1"

Write-Host "2. Starting OpsPilot Backend on port 8080..." -ForegroundColor Yellow
$backendCmd = "`$env:PATH = `"$env:PATH`"; cd `"$root\backend`"; & `"$pythonExe`" -m uvicorn app.main:app --port 8080 --host 127.0.0.1"

Write-Host "3. Starting OpsPilot Frontend on port 5173..." -ForegroundColor Yellow
$frontendCmd = "`$env:PATH = `"$env:PATH`"; cd `"$root\frontend`"; & `"$npmCmd`" run dev"

$hasWt = Get-Command wt.exe -ErrorAction SilentlyContinue
if ($hasWt) {
    Start-Process wt -ArgumentList "-w 0 new-tab --title ShopFlow-8000 -d `"$root\shopflow-test`" powershell -NoExit -Command `"$shopflowCmd`"" -ErrorAction SilentlyContinue
    Start-Process wt -ArgumentList "-w 0 new-tab --title OpsPilot-8080 -d `"$root\backend`" powershell -NoExit -Command `"$backendCmd`"" -ErrorAction SilentlyContinue
    Start-Process wt -ArgumentList "-w 0 new-tab --title OpsPilot-UI -d `"$root\frontend`" powershell -NoExit -Command `"$frontendCmd`"" -ErrorAction SilentlyContinue
} else {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $shopflowCmd
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd
}

Start-Sleep -Seconds 4
Write-Host "Opening OpsPilot Dashboard..." -ForegroundColor Green
Start-Process "http://localhost:5173"
Write-Host "Done! All services are active." -ForegroundColor Green
