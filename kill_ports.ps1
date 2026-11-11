param([switch]$Force)

if (-not $Force) {
    Write-Host "This stops the process listening on ports 8000, 8080, and 5173." -ForegroundColor Yellow
    Write-Host "Run .\kill_ports.ps1 -Force only when you intend to stop those processes." -ForegroundColor Yellow
    exit 2
}

Write-Host "Stopping listeners on ports 8000, 8080, and 5173 as requested..." -ForegroundColor Yellow

$ports = @(8000, 8080, 5173)
foreach ($port in $ports) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conns) {
            foreach ($c in $conns) {
                $pidToKill = $c.OwningProcess
                if ($pidToKill -gt 4) {
                    Write-Host "Freeing port $port (Terminating PID $pidToKill)..." -ForegroundColor Yellow
                    Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
                }
            }
        } else {
            Write-Host "Port $port is free." -ForegroundColor Gray
        }
    } catch {
        # ignore
    }
}

Write-Host "Requested listener processes have been stopped." -ForegroundColor Green
