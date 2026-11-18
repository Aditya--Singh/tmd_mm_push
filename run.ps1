<#
.SYNOPSIS
    Starts the whole platform in four windows: the backend of the hub, Peer
    Benchmarking, the news dashboard and the landing page.

.DESCRIPTION
    .\run.ps1

    Close the four windows to stop everything.

    What the backend says is written to backend\logs\backend.log. If the
    backend does not come up, the last of it is shown here, so the reason is
    never hidden in a window that is out of the way.
#>

$ErrorActionPreference = "Continue"

# How long the backend is given to answer before it is called a failure. A first
# start on a new machine is slow: every file of the environment is read for the
# first time, and the antivirus reads them as well.
$BackendWaitSeconds = 90

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path backend\.venv) -or -not (Test-Path benchmarking\.venv) -or -not (Test-Path sentinel\.venv) -or -not (Test-Path dataanalyzer\.venv)) {
    Write-Host "Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# The port the backend of the hub listens on. It is read from backend/.env, so
# that a machine where the port is already taken can use another one.
$BackendPort = 8000
$portLine = Select-String -Path (Join-Path $root 'backend\.env') -Pattern '^PORT=(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($portLine) { $BackendPort = [int]$portLine.Matches[0].Groups[1].Value }

# The port the Data Analyzer listens on. It is read from its own settings, so that a
# machine where the port is already taken can use another one.
$AnalyzerPort = 8095
$analyzerPortLine = Select-String -Path (Join-Path $root 'dataanalyzer\.env') -Pattern '^PORT=(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($analyzerPortLine) { $AnalyzerPort = [int]$analyzerPortLine.Matches[0].Groups[1].Value }

function Start-Service($name, $command, $workDir) {
    Write-Host "Starting $name"
    Start-Process -FilePath $command -ArgumentList $workDir -WorkingDirectory $root -WindowStyle Minimized
}

# --------------------------------------------------------------- the backend
# Everything the backend says is kept, and shown here if it does not come up.
$logDir = Join-Path $root 'backend\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$backendLog = Join-Path $logDir 'backend.log'
$backendStopped = Join-Path $logDir 'backend.stopped'

Remove-Item $backendLog -ErrorAction SilentlyContinue
Remove-Item $backendStopped -ErrorAction SilentlyContinue

# The path is put in single quotes for the window below, so a name with an
# apostrophe in it is escaped first.
$backendPath = $root.Replace("'", "''")
$backendLogPath = $backendLog.Replace("'", "''")
$backendStoppedPath = $backendStopped.Replace("'", "''")

$backendCommand = "Set-Location '$backendPath\backend'; " +
    ".\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort " +
    "2>&1 | Tee-Object -FilePath '$backendLogPath'; " +
    "Set-Content -Path '$backendStoppedPath' -Value 'stopped'"

Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", $backendCommand `
    -WorkingDirectory $root -WindowStyle Minimized

# The landing page cannot sign anybody in without the backend, so wait for it and
# say plainly when it does not come up.
$backendUp = $false
for ($attempt = 0; $attempt -lt $BackendWaitSeconds; $attempt++) {
    # Stop waiting as soon as the backend is gone: it will not come back.
    if (Test-Path $backendStopped) { break }

    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 2 -UseBasicParsing
        if ($health.StatusCode -eq 200) { $backendUp = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

if ($backendUp) {
    Write-Host 'The backend is up.' -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host 'The backend of the hub did not start, so signing in will not work.' -ForegroundColor Red
    Write-Host ''

    if (Test-Path $backendStopped) {
        Write-Host 'It stopped with an error. This is what it said:'
    } elseif (Test-NetConnection -ComputerName 127.0.0.1 -Port $BackendPort -InformationLevel Quiet -WarningAction SilentlyContinue) {
        Write-Host "Something else is on port $BackendPort, so the backend cannot start."
        Write-Host 'To see what it is:'
        Write-Host "    netstat -ano | findstr :$BackendPort"
        Write-Host 'Stop it, or give the backend another port in backend\.env (PORT=...)'
        Write-Host "and run 'python scripts\make_env.py' again."
    } else {
        Write-Host ("It is still starting after {0} seconds, so it is slow on this machine." -f $BackendWaitSeconds)
        Write-Host 'Start it by hand to watch it go:'
        Write-Host '    cd backend'
        Write-Host "    .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
    }

    Write-Host ''

    if (Test-Path $backendLog) {
        Get-Content $backendLog -Tail 25 | ForEach-Object { Write-Host "    $_" }
    }

    Write-Host ''
    Write-Host "The whole record is in $backendLog"
    Write-Host 'To have the whole platform checked: python scripts\doctor.py'
    exit 1
}

# Peer Benchmarking.
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "Set-Location '$root\benchmarking'; .\.venv\Scripts\python.exe -m kpibench.main" `
    -WorkingDirectory $root -WindowStyle Minimized

Start-Sleep -Seconds 2

# The Data Summarizer. It serves its own interface from the same address as its API.
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "Set-Location '$root\sentinel\backend'; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8090" `
    -WorkingDirectory $root -WindowStyle Minimized

Start-Sleep -Seconds 2

# The Data Analyzer. It serves its own interface from the same address as its API.
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "Set-Location '$root\dataanalyzer\backend'; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $AnalyzerPort" `
    -WorkingDirectory $root -WindowStyle Minimized

Start-Sleep -Seconds 2

# The news dashboard.
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev -- --host 127.0.0.1 --port 5173" `
    -WorkingDirectory $root -WindowStyle Minimized

# The landing page hub.
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "Set-Location '$root\landing'; npm run dev -- --host 127.0.0.1 --port 5174" `
    -WorkingDirectory $root -WindowStyle Minimized

Write-Host @"

The platform is starting.

    Landing page hub    http://localhost:5174
    News dashboard      http://localhost:5173
    Peer Benchmarking   http://localhost:8077
    Data Summarizer     http://localhost:8090
    Data Analyzer       http://localhost:$AnalyzerPort
    Backend and its API http://127.0.0.1:$BackendPort/docs

Sign in at http://localhost:5174 with admin / admin@tmd26

"@
