<#
.SYNOPSIS
    Starts the whole platform in four windows: the backend of the hub, Peer
    Benchmarking, the news dashboard and the landing page.

.DESCRIPTION
    .\run.ps1

    Close the four windows to stop everything.
#>

$ErrorActionPreference = "Continue"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path backend\.venv) -or -not (Test-Path benchmarking\.venv)) {
    Write-Host "Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

function Start-Service($name, $command, $workDir) {
    Write-Host "Starting $name"
    Start-Process -FilePath $command -ArgumentList $workDir -WorkingDirectory $root -WindowStyle Minimized
}

# The backend of the hub.
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000" `
    -WorkingDirectory $root -WindowStyle Minimized

# The landing page cannot sign anybody in without the backend, so wait for it and
# say plainly when it does not come up.
$backendUp = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2 -UseBasicParsing
        if ($health.StatusCode -eq 200) { $backendUp = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}

if ($backendUp) {
    Write-Host 'The backend is up.' -ForegroundColor Green
} else {
    Write-Host ''
    Write-Host 'The backend of the hub did not start, so signing in will not work.' -ForegroundColor Red
    Write-Host 'It is started by the window above; the reason is in that window.'
    Write-Host 'The usual causes are a missing settings file (run .\setup.ps1) or the'
    Write-Host 'port 8000 already being taken.'
    exit 1
}

# Peer Benchmarking.
Start-Process -FilePath "powershell" `
    -ArgumentList "-NoExit", "-Command", "Set-Location '$root\benchmarking'; .\.venv\Scripts\python.exe -m kpibench.main" `
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
    Backend and its API http://127.0.0.1:8000/docs

Sign in at http://localhost:5174 with admin / admin@tmd26

"@
