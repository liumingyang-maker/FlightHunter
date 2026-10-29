@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Prefer project venv Python via uv so pytest/ruff match CI.
where uv >nul 2>&1
if %errorlevel%==0 (
    uv run python tools\export_review_bundle.py %*
    goto :after
)

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 tools\export_review_bundle.py %*
) else (
    python tools\export_review_bundle.py %*
)

:after
if errorlevel 1 (
    echo.
    echo Export failed. Check the error above.
    pause
    exit /b 1
)
if exist "%~dp0review_exports" (
    start "" "%~dp0review_exports"
)
echo.
echo Upload the generated FlightHunter-review-*.zip to ChatGPT.
pause
