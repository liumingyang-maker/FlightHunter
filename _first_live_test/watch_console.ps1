param([Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$RunDir,
      [Parameter(Mandatory=$true)][string]$ToolDir)
$ErrorActionPreference = "Continue"
Write-Host "[MONITOR] 本地日志/SQLite 只读巡检。仅本机记录，不上传、不自动修代码。CTRL+C 停止。" -ForegroundColor Cyan
& $Python (Join-Path $ToolDir "monitor.py") --run-dir $RunDir --interval 4
Write-Host "[MONITOR] EXIT=$LASTEXITCODE" -ForegroundColor Yellow
