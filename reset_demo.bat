@echo off
echo ===================================================
echo   OpsPilot - Resetting Demo to Clean Baseline
echo ===================================================
echo.

echo Resetting ShopFlow and OpsPilot through the running backend...
curl.exe --fail --silent --show-error -X POST http://127.0.0.1:8080/api/reset
if errorlevel 1 (
  echo Reset failed. Start the backend and try again. No database files were deleted.
  exit /b 1
)
echo.
echo Clean demo state restored!
echo.
echo Ready for new live demo run!
