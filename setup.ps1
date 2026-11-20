<#
.SYNOPSIS
    One-time setup for the whole platform: the backend of the hub, Peer
    Benchmarking, the Data Summarizer, the Data Analyzer, the news dashboard
    and the landing page.

.DESCRIPTION
    Safe to run again. Open PowerShell in the repository folder and run:

        .\setup.ps1

    On Linux and macOS, with PowerShell 7 installed, the same script works:

        pwsh ./setup.ps1

    If the script is blocked, run it once with:

        powershell -ExecutionPolicy Bypass -File .\setup.ps1

    A step that fails does not stop the ones after it: the settings files and
    the accounts are written whatever else went wrong, and the problems are
    listed at the end.
#>

$ErrorActionPreference = "Continue"

function Say($text) { Write-Host "`n== $text" -ForegroundColor DarkRed }
function Note($text) { Write-Host "   $text" }

$problems = @()

function Problem($text) {
    $script:problems += $text
    Write-Host "   !! $text" -ForegroundColor Yellow
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Whether this is a Windows machine. Windows PowerShell 5 does not know the
# $IsWindows variable, and it only ever runs on Windows.
$OnWindows = ($PSVersionTable.PSVersion.Major -lt 6) -or ($IsWindows -eq $true)

# The interpreter of a virtual environment is in a different place on each
# system, and the same script has to work on both.
function The-Interpreter($folder) {
    if ($OnWindows) {
        return Join-Path $folder ".venv\Scripts\python.exe"
    }

    return Join-Path $folder ".venv/bin/python"
}

# The python of this machine. It has a name of its own, so that no function
# of this script can take its place by accident: PowerShell does not tell
# $SystemPython and $systempython apart.
$SystemPython = if ($env:PYTHON) { $env:PYTHON } else { "python" }

Say "1/8  Checking what is installed"
& $SystemPython --version
# The backend asks for Python 3.11 or newer, so that is what is checked here.
& $SystemPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Note "Python 3.11 or newer is needed."
    exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Note "Node.js is needed. See https://nodejs.org/"
    exit 1
}
node --version
npm --version

# The web applications are built with Vite, which needs Node 18 or newer. An
# older Node is reported plainly, because the failure otherwise shows up much
# later as a strange error from the build.
$nodeMajor = [int]((node -p "process.versions.node.split('.')[0]"))
if ($nodeMajor -lt 18) {
    Note "Node.js 18 or newer is needed to build the web applications."
    Note "See https://nodejs.org/ for a newer version."
    exit 1
}

# An environment that was made halfway is of no use, and the installation
# fails on it in a way that is hard to understand. A broken one is therefore
# removed and made again.
#
# The interpreter of the environment is not called $python here: PowerShell does
# not tell $python and $Python apart, and a name like that inside this function
# would take the place of the python of the machine.
function Make-TheEnvironment($folder) {
    $interpreter = The-Interpreter $folder

    if ((Test-Path (Join-Path $folder ".venv")) -and -not (Test-Path $interpreter)) {
        Note "The environment of $folder was made halfway. Making it again."
        Remove-Item (Join-Path $folder ".venv") -Recurse -Force -ErrorAction SilentlyContinue
    }

    if (-not (Test-Path (Join-Path $folder ".venv"))) {
        Push-Location $folder
        & $SystemPython -m venv .venv
        Pop-Location
    }

    # Without this, the steps after this one fail one after the other with a
    # message about a file that was never there.
    if (-not (Test-Path $interpreter)) {
        Problem "The environment of $folder could not be made. The python of this machine may be the wrong one; set `$env:PYTHON to the python you want to use."
        return $false
    }

    return $true
}

Say "2/8  The backend of the hub"
Make-TheEnvironment "backend" | Out-Null
$backendPython = The-Interpreter (Join-Path $root "backend")
Push-Location backend
& $backendPython -m pip install --upgrade pip wheel | Out-Null
& $backendPython -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    Note "The packages could not be downloaded. Behind a proxy, set `$env:HTTPS_PROXY first."
    exit 1
}
Pop-Location

Say "3/8  Peer Benchmarking"
Make-TheEnvironment "benchmarking" | Out-Null
$benchmarkingPython = The-Interpreter (Join-Path $root "benchmarking")
Push-Location benchmarking
& $benchmarkingPython -m pip install --upgrade pip wheel | Out-Null
& $benchmarkingPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Problem "Peer Benchmarking could not be installed. The hub still works without it."
}
Pop-Location

Say "4/8  The Data Summarizer (Regulatory Sentinel)"
Make-TheEnvironment "sentinel" | Out-Null
$sentinelPython = The-Interpreter (Join-Path $root "sentinel")
Push-Location sentinel
& $sentinelPython -m pip install --upgrade pip wheel | Out-Null
& $sentinelPython -m pip install -r backend/requirements-dev.txt
if ($LASTEXITCODE -ne 0) {
    Problem "The Data Summarizer could not be installed. The hub still works without it."
}
Pop-Location

Say "5/8  The Data Analyzer"
Make-TheEnvironment "dataanalyzer" | Out-Null
$analyzerPython = The-Interpreter (Join-Path $root "dataanalyzer")
Push-Location dataanalyzer
& $analyzerPython -m pip install --upgrade pip wheel | Out-Null
& $analyzerPython -m pip install -e ./backend
if ($LASTEXITCODE -ne 0) {
    Problem "The Data Analyzer could not be installed. The hub still works without it."
}
Pop-Location

Say "6/8  The four web applications"

# The packages are installed from the lock files, so that every machine ends up
# with the same versions. When the installation fails halfway, it leaves a
# broken folder behind, and a second attempt over it fails in the same way, so
# the folder is removed before the second attempt.
function Install-Packages($folder) {
    Push-Location $folder
    # The answer of npm is shown to the person running the setup, but it must not
    # become part of what this function returns: a function returns everything it
    # writes, and the caller asks only whether the installation failed.
    npm install --no-audit --no-fund | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Note "The installation of $folder was interrupted. Trying once more."
        if (Test-Path node_modules) { Remove-Item node_modules -Recurse -Force -ErrorAction SilentlyContinue }
        npm install --no-audit --no-fund | Out-Host
    }
    $failed = $LASTEXITCODE -ne 0
    Pop-Location
    return $failed
}

$newsFailed = Install-Packages "frontend"
if ($newsFailed) { Problem "The libraries of the news application could not be downloaded." }
$landingFailed = Install-Packages "landing"
if ($landingFailed) { Problem "The libraries of the landing page could not be downloaded." }
# The Data Summarizer serves its own interface from the same address as its API,
# so it is built once here rather than at every start.
Push-Location sentinel/frontend
if (-not (Test-Path node_modules)) { npm install --no-audit --no-fund }
npm run build
$sentinelFailed = $LASTEXITCODE -ne 0
Pop-Location
if ($sentinelFailed) {
    Problem "The interface of the Data Summarizer could not be built. It will show nothing until it is."
}

# The Data Analyzer serves its own interface from the same address as its API,
# so it is built once here rather than at every start.
Push-Location dataanalyzer/frontend
if (-not (Test-Path node_modules)) { npm install --no-audit --no-fund }
npm run build
$analyzerFailed = $LASTEXITCODE -ne 0
Pop-Location
if ($analyzerFailed) {
    Problem "The interface of the Data Analyzer could not be built. It will show nothing until it is."
}

Say "7/8  The settings files"
& $SystemPython scripts/make_env.py
if ($LASTEXITCODE -ne 0) { Problem "The settings files could not be written." }

Say "8/8  The demo accounts"
Push-Location backend
& $backendPython seed_users.py
$accountsFailed = $LASTEXITCODE -ne 0
Pop-Location
if ($accountsFailed) { Problem "The accounts could not be written. Nobody can sign in until they are." }

if ($problems.Count -eq 0) {
    Write-Host @"

Everything is ready.

Start the platform with:

    pwsh ./run.ps1

Check that everything is in place at any time:

    python scripts/doctor.py

Then open http://localhost:5174 and sign in with, for example:

    admin     / admin@tmd26        administrator in both applications
    analyst   / Pnb@12345          analyst, collects the figures
    approver  / Pnb@12345          approver, checks the figures
    gm        / Pnb@12345          general manager, reads them

"@
} else {
    Write-Host @"

The setup finished with problems. The rest of the platform is ready.

Start the platform with:

    pwsh ./run.ps1

Check what is still missing at any time:

    python scripts/doctor.py

The problems were:

"@

    foreach ($item in $problems) { Write-Host "  - $item" }

    Write-Host ""
    Write-Host "Run this setup again once the cause is sorted out."
}
