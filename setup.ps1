<#
.SYNOPSIS
    One-time setup for the whole platform: the backend of the hub, Peer
    Benchmarking, the news dashboard and the landing page.

.DESCRIPTION
    Safe to run again. Open PowerShell in the repository folder and run:

        .\setup.ps1

    If the script is blocked, run it once with:

        powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>

$ErrorActionPreference = "Stop"

function Say($text) { Write-Host "`n== $text" -ForegroundColor DarkRed }
function Note($text) { Write-Host "   $text" }

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

Say "1/6  Checking what is installed"
& $Python --version
& $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Note "Python 3.10 or newer is needed."
    exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Note "Node.js 20 or newer is needed. See https://nodejs.org/"
    exit 1
}
node --version
npm --version

Say "2/6  The backend of the hub"
Push-Location backend
if (-not (Test-Path .venv)) { & $Python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    Note "The packages could not be downloaded. Behind a proxy, set `$env:HTTPS_PROXY first."
    exit 1
}
Pop-Location

Say "3/6  Peer Benchmarking"
Push-Location benchmarking
if (-not (Test-Path .venv)) { & $Python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel | Out-Null
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Note "The packages could not be downloaded. Behind a proxy, set `$env:HTTPS_PROXY first."
    exit 1
}
Pop-Location

Say "4/6  The two web applications"
Push-Location frontend; npm install; Pop-Location
Push-Location landing; npm install; Pop-Location

Say "5/6  The settings files"
& $Python scripts/make_env.py

Say "6/6  The demo accounts"
Push-Location backend
& .\.venv\Scripts\python.exe seed_users.py
Pop-Location

Write-Host @"

Everything is ready.

Start the platform with:

    .\run.ps1

Then open http://localhost:5174 and sign in with, for example:

    admin     / admin@tmd26        administrator in both applications
    analyst   / Pnb@12345          analyst, collects the figures
    approver  / Pnb@12345          approver, checks the figures
    gm        / Pnb@12345          general manager, reads them

"@
