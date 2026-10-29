param([Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$Snapshot,
      [Parameter(Mandatory=$true)][string]$Logs,
      [int]$Port=8765)
$ErrorActionPreference = "Continue"
Set-Location $Snapshot
Write-Host "[WEB] FlightHunter http://127.0.0.1:$Port/; CTRL+C 停止" -ForegroundColor Cyan
& $Python -m app.cli web --host 127.0.0.1 --port $Port 2>&1 | Tee-Object -FilePath (Join-Path $Logs "web.log") -Append
Write-Host "[WEB] EXIT=$LASTEXITCODE" -ForegroundColor Yellow
