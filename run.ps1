<#
.SYNOPSIS
    Starts the whole platform: the backend of the hub, Peer Benchmarking, the
    Data Summarizer, the Data Analyzer, the news dashboard and the landing page.

.DESCRIPTION
    .\run.ps1

    On Windows six windows open, one for each service. Close them to stop
    everything.

    On Linux and macOS, with PowerShell 7 installed, the same script works:

        pwsh ./run.ps1

    There is no separate window to open there, so each service runs in the
    background and what it says is written to logs/<service>.log.

    What the backend says is written to backend/logs/backend.log. If the
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

# The shell the services are started in.
$Shell = if ($OnWindows) { "powershell" } else { "pwsh" }

# Whether something is listening on a port. The way to ask is different on each
# system, and Test-NetConnection only exists on Windows.
function Test-A-PortIsInUse($port) {
    $client = New-Object System.Net.Sockets.TcpClient

    try {
        $client.Connect("127.0.0.1", $port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

if (-not (Test-Path backend/.venv) -or -not (Test-Path benchmarking/.venv) -or -not (Test-Path sentinel/.venv) -or -not (Test-Path dataanalyzer/.venv)) {
    Write-Host "Run the setup first." -ForegroundColor Red
    if ($OnWindows) {
        Write-Host "    .\setup.ps1"
    } else {
        Write-Host "    pwsh ./setup.ps1"
    }
    exit 1
}

# The port the backend of the hub listens on. It is read from backend/.env, so
# that a machine where the port is already taken can use another one.
$BackendPort = 8000
$portLine = Select-String -Path (Join-Path $root 'backend/.env') -Pattern '^PORT=(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($portLine) { $BackendPort = [int]$portLine.Matches[0].Groups[1].Value }

# The port the Data Analyzer listens on. It is read from its own settings, so that a
# machine where the port is already taken can use another one.
$AnalyzerPort = 8095
$analyzerPortLine = Select-String -Path (Join-Path $root 'dataanalyzer/.env') -Pattern '^PORT=(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($analyzerPortLine) { $AnalyzerPort = [int]$analyzerPortLine.Matches[0].Groups[1].Value }

# The port the Data Summarizer listens on. It is read from its own settings for the
# same reason: the setup script moves a port that is already taken on this machine,
# and the summarizer has to be started on the port it was given.
$SummarizerPort = 8090
$summarizerPortLine = Select-String -Path (Join-Path $root 'sentinel/.env') -Pattern '^PORT=(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($summarizerPortLine) { $SummarizerPort = [int]$summarizerPortLine.Matches[0].Groups[1].Value }

# The port Peer Benchmarking listens on. It is only shown here: the application
# reads the port from its own settings.
$BenchmarkingPort = 8077
$benchmarkingPortLine = Select-String -Path (Join-Path $root 'benchmarking/.env') -Pattern '^PORT=(\d+)' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($benchmarkingPortLine) { $BenchmarkingPort = [int]$benchmarkingPortLine.Matches[0].Groups[1].Value }

# The path is put in single quotes for the windows below, so a name with an
# apostrophe in it is escaped first.
$rootEscaped = $root.Replace("'", "''")

# The services that are opened in the browser are told to answer on every
# address of the machine, so that they may be reached by the name of the hub
# and not only from the machine itself. The backend of the hub is not one of
# them: the browser reaches it through the landing page, and it stays on this
# machine.
$ServiceHost = '0.0.0.0'

# The name the hub is reached by, on the network of the bank.
$HubName = 'topmgmtdash.pnbbank.in'

# --------------------------------------------------------------- the backend
# Everything the backend says is kept, and shown here if it does not come up.
$logDir = Join-Path $root 'backend/logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$backendLog = Join-Path $logDir 'backend.log'
$backendStopped = Join-Path $logDir 'backend.stopped'

Remove-Item $backendLog -ErrorAction SilentlyContinue
Remove-Item $backendStopped -ErrorAction SilentlyContinue

# The path is put in single quotes for the window below, so a name with an
# apostrophe in it is escaped first.
$backendPath = $rootEscaped
$backendLogPath = $backendLog.Replace("'", "''")
$backendStoppedPath = $backendStopped.Replace("'", "''")
$backendPython = The-Interpreter (Join-Path $root "backend")
$backendPythonEscaped = $backendPython.Replace("'", "''")

$backendCommand = "Set-Location '$backendPath/backend'; " +
    "& '$backendPythonEscaped' -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort " +
    "2>&1 | Tee-Object -FilePath '$backendLogPath'; " +
    "Set-Content -Path '$backendStoppedPath' -Value 'stopped'"

if ($OnWindows) {
    Start-Process -FilePath "powershell" `
        -ArgumentList "-NoExit", "-Command", $backendCommand `
        -WorkingDirectory $root -WindowStyle Minimized
} else {
    # There is no separate window on this system, so the service runs in the
    # background and what it says is written to the log.
    Start-Process -FilePath $Shell `
        -ArgumentList "-NoProfile", "-Command", $backendCommand `
        -WorkingDirectory $root -NoNewWindow
}

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
    } elseif (Test-A-PortIsInUse $BackendPort) {
        Write-Host "Something else is on port $BackendPort, so the backend cannot start."
        Write-Host 'To see what it is:'
        if ($OnWindows) {
            Write-Host "    netstat -ano | findstr :$BackendPort"
        } else {
            Write-Host "    ss -tlnp | grep :$BackendPort"
        }
        Write-Host 'Stop it, or give the backend another port in backend/.env (PORT=...)'
        Write-Host "and run 'python scripts/make_env.py' again."
    } else {
        Write-Host ("It is still starting after {0} seconds, so it is slow on this machine." -f $BackendWaitSeconds)
        Write-Host 'Start it by hand to watch it go:'
        Write-Host '    cd backend'
        Write-Host "    $backendPython -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
    }

    Write-Host ''

    if (Test-Path $backendLog) {
        Get-Content $backendLog -Tail 25 | ForEach-Object { Write-Host "    $_" }
    }

    Write-Host ''
    Write-Host "The whole record is in $backendLog"
    Write-Host 'To have the whole platform checked: python scripts/doctor.py'
    exit 1
}

# Every other service is started the same way: in a window of its own on
# Windows, in the background on the other systems.
function Start-A-Service($name, $command, $workDir) {
    Write-Host "Starting $name"

    if ($OnWindows) {
        Start-Process -FilePath "powershell" `
            -ArgumentList "-NoExit", "-Command", $command `
            -WorkingDirectory $root -WindowStyle Minimized
    } else {
        $serviceLog = Join-Path $logDir "$name.log"

        Start-Process -FilePath $Shell `
            -ArgumentList "-NoProfile", "-Command", $command `
            -WorkingDirectory $workDir -NoNewWindow `
            -RedirectStandardOutput $serviceLog -RedirectStandardError "$serviceLog.err"
    }
}

# Peer Benchmarking.
$benchmarkingPython = (The-Interpreter (Join-Path $root "benchmarking")).Replace("'", "''")
Start-A-Service "benchmarking" "Set-Location '$rootEscaped/benchmarking'; & '$benchmarkingPython' -m kpibench.main" (Join-Path $root "benchmarking")

Start-Sleep -Seconds 2

# The Data Summarizer. It serves its own interface from the same address as its API.
$sentinelPython = (The-Interpreter (Join-Path $root "sentinel")).Replace("'", "''")
Start-A-Service "summarizer" "Set-Location '$rootEscaped/sentinel/backend'; & '$sentinelPython' -m uvicorn app.main:app --host $ServiceHost --port $SummarizerPort" (Join-Path $root "sentinel/backend")

Start-Sleep -Seconds 2

# The Data Analyzer. It serves its own interface from the same address as its API.
$analyzerPython = (The-Interpreter (Join-Path $root "dataanalyzer")).Replace("'", "''")
Start-A-Service "analyzer" "Set-Location '$rootEscaped/dataanalyzer/backend'; & '$analyzerPython' -m uvicorn app.main:app --host $ServiceHost --port $AnalyzerPort" (Join-Path $root "dataanalyzer/backend")

Start-Sleep -Seconds 2

# The news dashboard.
Start-A-Service "news" "Set-Location '$rootEscaped/frontend'; npm run dev -- --host $ServiceHost --port 5173" (Join-Path $root "frontend")

# The landing page hub.
Start-A-Service "landing" "Set-Location '$rootEscaped/landing'; npm run dev -- --host $ServiceHost --port 5174" (Join-Path $root "landing")

Write-Host @"

The platform is starting.

    Landing page hub    http://${HubName}:5174
    News dashboard      http://${HubName}:5173
    Peer Benchmarking   http://${HubName}:$BenchmarkingPort
    Data Summarizer     http://${HubName}:$SummarizerPort
    Data Analyzer       http://${HubName}:$AnalyzerPort
    Backend and its API http://127.0.0.1:$BackendPort/docs

Sign in at http://${HubName}:5174 with admin / admin@tmd26

The name $HubName has to answer to this machine. Add it to the hosts file of
the machine, and let the ports through the firewall.

"@
