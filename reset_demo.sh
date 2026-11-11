#!/usr/bin/env bash
set -e

echo "==================================================="
echo "  OpsPilot - Resetting Demo to Clean Baseline"
echo "==================================================="
echo ""

echo "Resetting ShopFlow and OpsPilot through the running backend..."
if ! curl --fail --silent --show-error -X POST http://127.0.0.1:8080/api/reset; then
  echo "Reset failed. Start the backend and try again. No database files were deleted." >&2
  exit 1
fi
echo ""
echo "Clean demo state restored!"
echo "Ready for new demo run."
