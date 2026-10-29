# FlightHunter first isolated live run; run this from _first_live_test inside your Git repository.
param([string]$ExpectedHead = "1d69efb", [int]$Port = 8765)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "缺少 .venv\Scripts\python.exe；请先在仓库执行 uv sync。" }
$Head = ((& git -C $Repo rev-parse HEAD) | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "无法读取 git HEAD；请确保在 Git 仓库内解压 _first_live_test 文件夹。" }
if (-not $Head.StartsWith($ExpectedHead)) {
  throw "当前 HEAD=$Head 与本测试包审核基线 $ExpectedHead 不一致。请核对本次要测试的版本，不要强行覆盖代码。"
}
$PortInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($PortInUse) { throw "端口 $Port 已被占用。请先停止旧 FlightHunter Web，避免监控错误的程序实例。" }
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunDir = Join-Path $Repo "data\live_tests\$Timestamp"
$Snapshot = Join-Path $RunDir "snapshot"
$Logs = Join-Path $RunDir "logs"
New-Item -ItemType Directory -Force -Path $RunDir, $Snapshot, $Logs | Out-Null
$Archive = Join-Path $RunDir "source_HEAD.zip"
& git -C $Repo archive --format=zip HEAD -o $Archive
if ($LASTEXITCODE -ne 0) { throw "git archive 失败" }
Expand-Archive -Path $Archive -DestinationPath $Snapshot -Force
$Config = @"
# First live-run isolated config; not the user's normal DB
app:
  demo_mode: false
  web_host: 127.0.0.1
  web_port: $Port
  telemetry_enabled: false
storage:
  sqlite_path: ./data/flighthunter-live-test.db
sources:
  per_domain_concurrency: 1
  min_seconds_between_requests_per_domain: 10
  obey_robots_and_site_terms: true
  max_runtime_seconds_per_page: 20
entry:
  auto_submission_globally_enabled: false
  default_mode: PREFILL_AND_REVIEW
trip_benefits:
  auto_claim_globally_enabled: false
  benefit_claim_policy: PREFILL_AND_REVIEW
notifications:
  email_integration_enabled: false
cloud:
  public_discovery_enabled: false
  github_actions_schedule_enabled: false
  cloudflare_d1_sync_enabled: false
  upload_private_user_data: false
airfare_radar:
  quote_provider_enabled: false
"@
$Config | Set-Content -Path (Join-Path $Snapshot "config.yaml") -Encoding utf8
"HEAD=$Head`nRUN_DIR=$RunDir`nSOURCE_SNAPSHOT=$Snapshot`nPORT=$Port" | Set-Content (Join-Path $RunDir "run_manifest.txt") -Encoding utf8
Write-Host "[ISOLATED] snapshot $Snapshot" -ForegroundColor Cyan
Write-Host "[ISOLATED] DB at snapshot/data/flighthunter-live-test.db; will NOT touch repo/data/flighthunter.db" -ForegroundColor Cyan
$ErrorActionPreference = "Continue" # Alembic may log to stderr on Windows PowerShell 5.x
Push-Location $Snapshot
try {
  & $Python -m app.cli migrate 2>&1 | Tee-Object -FilePath (Join-Path $Logs "setup.log") -Append
  if ($LASTEXITCODE -ne 0) { throw "数据库迁移失败，已停止真实抓取。" }
  & $Python (Join-Path $PSScriptRoot "bootstrap_sources.py") 2>&1 | Tee-Object -FilePath (Join-Path $Logs "setup.log") -Append
  if ($LASTEXITCODE -ne 0) { throw "数据库初始化/迁移版本校验失败，已停止真实抓取。" }
} finally { Pop-Location }

$WebScript = Join-Path $PSScriptRoot "web_console.ps1"
$MonitorScript = Join-Path $PSScriptRoot "watch_console.ps1"
$SweepScript = Join-Path $PSScriptRoot "run_sweep.ps1"
Start-Process powershell.exe -WorkingDirectory $Snapshot -ArgumentList "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$WebScript`" -Python `"$Python`" -Snapshot `"$Snapshot`" -Logs `"$Logs`" -Port $Port"
Start-Process powershell.exe -WorkingDirectory $Snapshot -ArgumentList "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$MonitorScript`" -Python `"$Python`" -RunDir `"$RunDir`" -ToolDir `"$PSScriptRoot`""
Start-Process powershell.exe -WorkingDirectory $Snapshot -ArgumentList "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$SweepScript`" -Python `"$Python`" -Snapshot `"$Snapshot`" -Logs `"$Logs`" -RunDir `"$RunDir`" -ToolDir `"$PSScriptRoot`""
Write-Host "`n三窗口已启动：Web / 监控 / 限量真实抓取。" -ForegroundColor Green
Write-Host "访问 http://127.0.0.1:$Port/ （登录凭据在隔离 snapshot/data/auth.json，只能本机使用、不要粘贴给 AI）"
Write-Host "结果将写入 $RunDir\RESULTS.md；失败任务不会自动无限重试。"
