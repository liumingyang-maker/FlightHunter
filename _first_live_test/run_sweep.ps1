param([Parameter(Mandatory=$true)][string]$Python,
      [Parameter(Mandatory=$true)][string]$Snapshot,
      [Parameter(Mandatory=$true)][string]$Logs,
      [Parameter(Mandatory=$true)][string]$RunDir,
      [Parameter(Mandatory=$true)][string]$ToolDir)
$ErrorActionPreference = "Continue"
Set-Location $Snapshot
$Log = Join-Path $Logs "sweep.log"
function Run-Stage {
  param([string]$Name, [string[]]$Arguments)
  "=== START $Name ===" | Tee-Object -FilePath $Log -Append
  & $Python @Arguments 2>&1 | Tee-Object -FilePath $Log -Append
  $ExitCode = $LASTEXITCODE
  "=== RESULT $Name EXIT=$ExitCode ===" | Tee-Object -FilePath $Log -Append
}

Write-Host "[SWEEP] Limited live public read test. No submit/pay/claim." -ForegroundColor Cyan
Run-Stage "doctor" @("-m","app.cli","doctor")
Run-Stage "dry_raffle" @("-m","app.cli","discover","--module","raffle","--dry-run","--limit","1")
Run-Stage "dry_trip" @("-m","app.cli","discover","--module","trip","--dry-run","--limit","1")
Run-Stage "dry_fare" @("-m","app.cli","discover","--module","fare","--dry-run","--limit","1")
Run-Stage "live_raffle" @("-m","app.cli","discover","--module","raffle","--execute","--limit","1")
Start-Sleep -Seconds 12
Run-Stage "raffle_provenance" @("-m","app.cli","raffle-provenance","--limit","1")
Start-Sleep -Seconds 12
Run-Stage "live_trip" @("-m","app.cli","discover","--module","trip","--execute","--limit","1")
Start-Sleep -Seconds 12
Run-Stage "jp_benefits_demo_trip" @("-m","app.cli","jp-benefits-scan")
Start-Sleep -Seconds 12
Run-Stage "live_fare" @("-m","app.cli","discover","--module","fare","--execute","--limit","1")
Start-Sleep -Seconds 4
"=== SWEEP COMPLETE ===" | Tee-Object -FilePath $Log -Append
& $Python (Join-Path $ToolDir "monitor.py") --run-dir $RunDir --once
& $Python (Join-Path $ToolDir "export_results.py") --run-dir $RunDir
Write-Host "[SWEEP] Results: $RunDir\RESULTS.md" -ForegroundColor Green
