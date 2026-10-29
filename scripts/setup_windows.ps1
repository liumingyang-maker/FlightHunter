# FlightHunter Windows 11 初始化脚本
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== FlightHunter 初始化 ==" -ForegroundColor Cyan

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Error "需要安装 uv: https://docs.astral.sh/uv/"
}

uv sync
uv run python -m app.cli doctor
uv run python -m app.cli seed --safe `
  --travel-plan fixtures/travel_plan.example.json `
  --fare-signal fixtures/fare_signal.example.json
uv run python -m app.cli discover --dry-run

Write-Host ""
Write-Host "启动 Web:" -ForegroundColor Green
Write-Host "  uv run python -m app.cli web --host 127.0.0.1 --port 8765"
