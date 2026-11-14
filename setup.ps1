<#
.SYNOPSIS
    One-time setup for the whole platform: the backend of the hub, Peer
    Benchmarking, the Data Summarizer, the news dashboard and the landing page.

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

Say "1/7  Checking what is installed"
& $Python --version
# The backend asks for Python 3.11 or newer, so that is what is checked here.
& $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Note "Python 3.11 or newer is needed."
    exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Note "Node.js 20 or newer is needed. See https://nodejs.org/"
    exit 1
}
node --version
npm --version

Say "2/7  The backend of the hub"
Push-Location backend
if (-not (Test-Path .venv)) { & $Python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    Note "The packages could not be downloaded. Behind a proxy, set `$env:HTTPS_PROXY first."
    exit 1
}
Pop-Location

Say "3/7  Peer Benchmarking"
Push-Location benchmarking
if (-not (Test-Path .venv)) { & $Python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel | Out-Null
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Note "The packages could not be downloaded. Behind a proxy, set `$env:HTTPS_PROXY first."
    exit 1
}
Pop-Location

Say "4/7  The Data Summarizer (Regulatory Sentinel)"
Push-Location sentinel
if (-not (Test-Path .venv)) { & $Python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel | Out-Null
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
if ($LASTEXITCODE -ne 0) {
    Note "The packages could not be downloaded. Behind a proxy, set `$env:HTTPS_PROXY first."
    exit 1
}
Pop-Location

Say "5/7  The three web applications"
Push-Location frontend; npm install; $newsFailed = $LASTEXITCODE -ne 0; Pop-Location
Push-Location landing; npm install; $landingFailed = $LASTEXITCODE -ne 0; Pop-Location
# The Data Summarizer serves its own interface from the same address as its API,
# so it is built once here rather than at every start.
Push-Location sentinel\frontend
if (-not (Test-Path node_modules)) { npm install }
npm run build
$sentinelFailed = $LASTEXITCODE -ne 0
Pop-Location
if ($newsFailed -or $landingFailed -or $sentinelFailed) {
    Note "The libraries could not be downloaded, or the interface could not be built."
    Note "Behind a proxy, set `$env:HTTPS_PROXY first."
    exit 1
}

Say "6/7  The settings files"
& $Python scripts/make_env.py
if ($LASTEXITCODE -ne 0) {
    Note "The settings files could not be written. The text above says why."
    exit 1
}

Say "7/7  The demo accounts"
Push-Location backend
& .\.venv\Scripts\python.exe seed_users.py
$accountsFailed = $LASTEXITCODE -ne 0
Pop-Location
if ($accountsFailed) {
    Note "The accounts could not be written. The text above says why."
    exit 1
}

Write-Host @"

Everything is ready.

Start the platform with:

    .\run.ps1

Check that everything is in place at any time:

    python scripts\doctor.py

Then open http://localhost:5174 and sign in with, for example:

    admin     / admin@tmd26        administrator in both applications
    analyst   / Pnb@12345          analyst, collects the figures
    approver  / Pnb@12345          approver, checks the figures
    gm        / Pnb@12345          general manager, reads them

"@
