# FlightHunter 当前用户计划任务安装（无需管理员）
# 用法: pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\install_user_worker_task.ps1
param(
  [string]$Python = "",
  [int]$IntervalSeconds = 3600
)
$ErrorActionPreference = "Stop"
$Repo = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $Python) {
  $Python = Join-Path $Repo ".venv\Scripts\python.exe"
}
if (-not (Test-Path $Python)) { throw "Missing python: $Python" }
# 方案A：当前用户启动文件夹（无需管理员、无需计划任务权限）
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "FlightHunterWorker.bat"
$cmd = @"
@echo off
cd /d "$Repo"
start "" pwsh -NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -Command "& '$Python' -m app.cli worker --execute --interval-seconds $IntervalSeconds"
"@
Set-Content -Path $lnk -Value $cmd -Encoding ascii
Write-Host "Startup shortcut: $lnk"

# 方案B：尝试用户级计划任务（部分环境需额外权限）
try {
  $Action = New-ScheduledTaskAction -Execute "pwsh.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"& '$Python' -m app.cli worker --execute --interval-seconds $IntervalSeconds`"" -WorkingDirectory $Repo
  $Trigger = New-ScheduledTaskTrigger -AtLogOn
  $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
  Register-ScheduledTask -TaskName "FlightHunterWorker" -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
  Write-Host "Also registered ScheduledTask FlightHunterWorker."
} catch {
  Write-Host "ScheduledTask skipped (permission): $($_.Exception.Message)"
  Write-Host "Startup folder method remains active."
}
Write-Host "Python: $Python"
Write-Host "Manual start: & '$Python' -m app.cli worker --execute"
