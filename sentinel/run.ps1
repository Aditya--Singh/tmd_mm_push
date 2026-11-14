<#
  Run PNB Regulatory Sentinel on Windows WITHOUT Docker.
    powershell -ExecutionPolicy Bypass -File .\run.ps1          # build the UI and start on http://localhost:8090
    powershell -ExecutionPolicy Bypass -File .\run.ps1 test     # run the automatic tests
  Needs: Python 3.12 (python.org, tick "Add python.exe to PATH") and Node.js 22 LTS (nodejs.org).
  Ollama for Windows (ollama.com) for the AI models, or point LLM_BASE_URL in .env at the GB10.
#>
param([ValidateSet("serve", "test")][string]$Mode = "serve")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Run($exe, [string[]]$argv) {
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $exe $($argv -join ' ')" }
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example. Check it with: notepad .env  - then run this script again." -ForegroundColor Yellow
    exit 1
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$ready = Join-Path $PSScriptRoot ".venv\.ready"
if (-not (Test-Path $ready)) {
    Write-Host "First run: installing the Python parts (5-10 minutes)..." -ForegroundColor Cyan
    if (-not (Test-Path $py)) {
        $use312 = $false
        if (Get-Command py -ErrorAction SilentlyContinue) { & py -3.12 --version *> $null; $use312 = ($LASTEXITCODE -eq 0) }
        if ($use312) { Run "py" @("-3.12", "-m", "venv", ".venv") }
        else { Run "python" @("-m", "venv", ".venv") }
    }
    Run $py @("-m", "pip", "install", "--upgrade", "pip")
    Run $py @("-m", "pip", "install", "-r", "backend\requirements-dev.txt")
    Run $py @("-m", "playwright", "install", "chromium")
    New-Item -ItemType File -Path $ready -Force | Out-Null
}

$port = 8090
$line = Select-String -Path .env -Pattern '^PORT=(\d+)' | Select-Object -First 1
if ($line) { $port = [int]$line.Matches[0].Groups[1].Value }

if ($Mode -eq "test") {
    Push-Location backend; try { Run $py @("-m", "pytest", "-q") } finally { Pop-Location }
    exit 0
}

Push-Location frontend
try {
    if (-not (Test-Path node_modules)) { Run "npm.cmd" @("ci", "--no-audit", "--no-fund") }
    Run "npm.cmd" @("run", "build")
} finally { Pop-Location }

Write-Host "Starting on http://localhost:$port  (press Ctrl + C to stop)" -ForegroundColor Green
Push-Location backend
try { Run $py @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$port", "--workers", "1") }
finally { Pop-Location }
