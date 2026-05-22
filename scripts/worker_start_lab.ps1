param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    Write-Host ".venv is missing. Run scripts/worker_setup.ps1 first." -ForegroundColor Red
    exit 1
}

$localIp = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -First 1 -ExpandProperty IPAddress)

Write-Host "Starting cadybara worker lab..." -ForegroundColor Green
Write-Host "Local URL:   http://127.0.0.1:$Port/lab/"
if ($localIp) {
    Write-Host "Network URL: http://$localIp`:$Port/lab/"
}
Write-Host "Use Stop After Current in the UI to pause a run safely."

& .\.venv\Scripts\cadybara.exe lab --host $HostAddress --port $Port
