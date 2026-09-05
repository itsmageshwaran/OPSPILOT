@echo off
echo ===================================================
echo   OpsPilot - Starting Complete Incident Command Center
echo ===================================================
echo.

echo 1. Starting ShopFlow Microservices on port 8000...
start "ShopFlow (Port 8000)" cmd /k "cd /d %~dp0shopflow-test && python -m uvicorn services.api_gateway.main:app --port 8000 --host 127.0.0.1"

echo 2. Starting OpsPilot Backend on port 8080...
start "OpsPilot Backend (Port 8080)" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --port 8080 --host 127.0.0.1"

echo 3. Starting OpsPilot React Frontend on port 5173...
start "OpsPilot Frontend (Port 5173)" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo All services launched! Opening OpsPilot in browser...
timeout /t 3 >nul
start http://localhost:5173
echo.
echo Done! Keep the opened terminal windows running.
