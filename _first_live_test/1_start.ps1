# FlightHunter first isolated live run
param([string]$ExpectedHead = "e029100", [int]$Port = 8765)
$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Missing .venv python; run uv sync first." }
$Head = ((& git -C $Repo rev-parse HEAD) | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "Cannot read git HEAD." }
if (-not $Head.StartsWith($ExpectedHead)) {
  throw "HEAD=$Head does not start with ExpectedHead=$ExpectedHead"
}
$PortInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($PortInUse) { throw "Port $Port already in use." }
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunDir = Join-Path $Repo "data\live_tests\$Timestamp"
$Snapshot = Join-Path $RunDir "snapshot"
$Logs = Join-Path $RunDir "logs"
New-Item -ItemType Directory -Force -Path $RunDir, $Snapshot, $Logs | Out-Null
$Archive = Join-Path $RunDir "source_HEAD.zip"
& git -C $Repo archive --format=zip HEAD -o $Archive
if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
Expand-Archive -Path $Archive -DestinationPath $Snapshot -Force
$Config = @"
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
Write-Host "[ISOLATED] DB at snapshot/data/flighthunter-live-test.db" -ForegroundColor Cyan
$ErrorActionPreference = "Continue"
Push-Location $Snapshot
try {
  & $Python -m app.cli migrate 2>&1 | Tee-Object -FilePath (Join-Path $Logs "setup.log") -Append
  if ($LASTEXITCODE -ne 0) { throw "DB migrate failed." }
  & $Python (Join-Path $PSScriptRoot "bootstrap_sources.py") 2>&1 | Tee-Object -FilePath (Join-Path $Logs "setup.log") -Append
  if ($LASTEXITCODE -ne 0) { throw "bootstrap_sources failed." }
} finally { Pop-Location }

$Pwsh = Get-Command pwsh.exe -ErrorAction SilentlyContinue
if (-not $Pwsh) { $Pwsh = Get-Command pwsh -ErrorAction SilentlyContinue }
if (-not $Pwsh) { throw "pwsh (PowerShell 7) not found; install PowerShell 7 before live run." }
$PwshExe = $Pwsh.Source
Write-Host "[PWSH] Using PowerShell 7: $PwshExe" -ForegroundColor Cyan
$WebScript = Join-Path $PSScriptRoot "web_console.ps1"
$MonitorScript = Join-Path $PSScriptRoot "watch_console.ps1"
$SweepScript = Join-Path $PSScriptRoot "run_sweep.ps1"
Start-Process $PwshExe -WorkingDirectory $Snapshot -ArgumentList "-NoExit","-NoProfile","-ExecutionPolicy","Bypass","-File",$WebScript,"-Python",$Python,"-Snapshot",$Snapshot,"-Logs",$Logs,"-Port","$Port"
Start-Process $PwshExe -WorkingDirectory $Snapshot -ArgumentList "-NoExit","-NoProfile","-ExecutionPolicy","Bypass","-File",$MonitorScript,"-Python",$Python,"-RunDir",$RunDir,"-ToolDir",$PSScriptRoot
Start-Process $PwshExe -WorkingDirectory $Snapshot -ArgumentList "-NoExit","-NoProfile","-ExecutionPolicy","Bypass","-File",$SweepScript,"-Python",$Python,"-Snapshot",$Snapshot,"-Logs",$Logs,"-RunDir",$RunDir,"-ToolDir",$PSScriptRoot
Write-Host "Three pwsh windows started: Web / Monitor / Sweep." -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:$Port/"
Write-Host "Results: $RunDir\RESULTS.md"
