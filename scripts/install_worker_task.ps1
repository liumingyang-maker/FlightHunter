# FlightHunter Windows 后台服务安装（任务计划程序）
# 以当前用户登录时启动 worker；需管理员权限写计划任务时可尝试提升。
param(
  [string]$ProjectRoot = (Get-Location).Path,
  [int]$IntervalSeconds = 3600,
  [switch]$Execute,
  [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$TaskName = "FlightHunterWorker"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

if ($Uninstall) {
  schtasks /Delete /TN $TaskName /F 2>$null
  Write-Host "已删除计划任务 $TaskName" -ForegroundColor Yellow
  exit 0
}

$exeFlag = if ($Execute) { "--execute" } else { "" }
$argList = "-m app.cli worker --interval-seconds $IntervalSeconds $exeFlag"
$Action = New-ScheduledTaskAction -Execute $Python -Argument $argList -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Write-Host "已注册计划任务 $TaskName（interval=${IntervalSeconds}s, execute=$Execute）" -ForegroundColor Green
Write-Host "可手动: schtasks /Run /TN $TaskName"
Write-Host "日志请查看控制台或 data/ 目录；worker 默认 dry-run，需 --Execute 才抓取。"
