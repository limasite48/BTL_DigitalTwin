# Master Orchestrator for _simReal System (Web Control Center Edition)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host "          STARTING SIMREAL SYSTEM MODULES (_simReal)" -ForegroundColor Cyan
Write-Host "=======================================================================" -ForegroundColor Cyan
Write-Host ""

$simDir = $PSScriptRoot
$logDir = "$simDir\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$dockerComposeFile = "$simDir\iot-server\src\main\docker\compose\docker-compose.yml"

# Helper function to check TCP port connection
function Test-PortOpen ($hostName, $port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $asyncResult = $client.BeginConnect($hostName, $port, $null, $null)
        $waitHandle = $asyncResult.AsyncWaitHandle.WaitOne(1000, $false)
        if (-not $waitHandle) {
            $client.Close()
            return $false
        }
        $client.EndConnect($asyncResult)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

# Safe Shutdown function
function Stop-AllSimReal {
    Write-Host "`n=======================================================================" -ForegroundColor Red
    Write-Host "              SHUTTING DOWN ALL SIMREAL SERVICES SAFELY...            " -ForegroundColor Red
    Write-Host "=======================================================================" -ForegroundColor Red
    
    Write-Host "[1/3] Closing Background Simulator & Dashboard Processes..." -ForegroundColor Gray
    if ($global:dashProc -and -not $global:dashProc.HasExited) { taskkill /F /T /PID $global:dashProc.Id 2>$null }
    if ($global:weatherProc -and -not $global:weatherProc.HasExited) { taskkill /F /T /PID $global:weatherProc.Id 2>$null }
    if ($global:gatewayProc -and -not $global:gatewayProc.HasExited) { taskkill /F /T /PID $global:gatewayProc.Id 2>$null }
    if ($global:objectProc -and -not $global:objectProc.HasExited) { taskkill /F /T /PID $global:objectProc.Id 2>$null }

    Write-Host "[2/3] Terminating Python & Java Processes..." -ForegroundColor Gray
    Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name uv -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Get-Process -Name java -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

    Write-Host "[3/3] Stopping Docker Containers (Postgres, Mosquitto, Redis)..." -ForegroundColor Gray
    docker compose -f "$dockerComposeFile" down

    Write-Host "`n[SUCCESS] All _simReal modules closed safely. Goodbye!" -ForegroundColor Green
}

# 1. Start Docker Containers (Postgres, Mosquitto, Redis)
Write-Host "[1/5] Starting Docker Containers (Postgres, Mosquitto, Redis)..." -ForegroundColor Green
docker compose -f "$dockerComposeFile" up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR] Failed to start Docker containers! Please ensure Docker Desktop is running." -ForegroundColor Red
    exit 1
}

# Check Mosquitto (1883) & Postgres (5432) port readiness
Write-Host "Checking MQTT Broker (1883) & Postgres (5432) port readiness..." -ForegroundColor Gray
$dockerReady = $false
for ($i = 1; $i -le 15; $i++) {
    $mqttOk = Test-PortOpen "localhost" 1883
    $pgOk   = Test-PortOpen "localhost" 5432
    if ($mqttOk -and $pgOk) {
        $dockerReady = $true
        break
    }
    Start-Sleep -Seconds 1
}

if (-not $dockerReady) {
    Write-Host "`n[ERROR] Docker containers failed to bind ports 1883/5432 in time!" -ForegroundColor Red
    Stop-AllSimReal
    exit 1
}
Write-Host "[OK] Mosquitto MQTT Broker & PostgreSQL are ONLINE." -ForegroundColor Green

# 2. Start Weather Simulator Engine (Headless Background Process)
Write-Host "`n[2/5] Starting Weather Simulator Engine (Headless)..." -ForegroundColor Green
$global:weatherProc = Start-Process cmd -ArgumentList "/c cd /d `"$simDir\weather-simulate`" && uv run main.py" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2

# 3. Start IoT Gateway Simulator (Headless Background Process)
Write-Host "[3/5] Starting IoT Gateway Simulator (Headless)..." -ForegroundColor Green
$global:gatewayProc = Start-Process cmd -ArgumentList "/c cd /d `"$simDir\iot-gateway-simulate`" && uv run main.py" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2

# 4. Start IoT Object Simulator (Headless Background Process)
Write-Host "[4/5] Starting IoT Object Simulator (Headless)..." -ForegroundColor Green
$global:objectProc = Start-Process cmd -ArgumentList "/c cd /d `"$simDir\iot-object-simulate`" && uv run main.py" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2

# 5. Start Web Control Dashboard Server (Port 8090)
Write-Host "[5/5] Launching Web Control Dashboard (http://localhost:8090)..." -ForegroundColor Green
$global:dashProc = Start-Process cmd -ArgumentList "/c cd /d `"$simDir\iot-gateway-simulate`" && uv run python `"$simDir\web_dashboard\server.py`"" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2

# Start Spring Boot Backend
Write-Host "Starting Spring Boot Backend (http://localhost:8080)..." -ForegroundColor Green
$backendLog = "$logDir\backend.log"
$backendErr = "$logDir\backend_error.log"
$backendProc = Start-Process cmd -ArgumentList "/c cd /d `"$simDir\iot-server`" && .\gradlew.bat bootRun" -NoNewWindow -RedirectStandardOutput $backendLog -RedirectStandardError $backendErr -PassThru

# Poll Backend Health Check
Write-Host "Waiting for Spring Boot Backend health check on http://localhost:8080..." -ForegroundColor Gray
$backendReady = $false
for ($i = 1; $i -le 40; $i++) {
    Start-Sleep -Seconds 1
    if ($backendProc.HasExited) {
        break
    }
    try {
        $res = Invoke-WebRequest -Uri "http://localhost:8080/actuator/health" -UseBasicParsing -TimeoutSec 1 -ErrorAction SilentlyContinue
        if ($res.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {
        if (Test-PortOpen "localhost" 8080) {
            $backendReady = $true
            break
        }
    }
}

if (-not $backendReady) {
    Write-Host "`n=======================================================================" -ForegroundColor Red
    Write-Host "[ERROR] Spring Boot Backend failed to start or health check timed out!" -ForegroundColor Red
    Write-Host "=======================================================================" -ForegroundColor Red
    if (Test-Path $backendLog) {
        Write-Host "--- LAST 15 LINES OF logs/backend.log ---" -ForegroundColor Yellow
        Get-Content $backendLog -Tail 15 | Write-Host -ForegroundColor Yellow
    }
    if (Test-Path $backendErr) {
        Write-Host "--- LAST 10 LINES OF logs/backend_error.log ---" -ForegroundColor Red
        Get-Content $backendErr -Tail 10 | Write-Host -ForegroundColor Red
    }
    Stop-AllSimReal
    exit 1
}

# Auto-open browser at http://localhost:8090
Start-Process "http://localhost:8090"

Write-Host "`n=======================================================================" -ForegroundColor Green
Write-Host "         [SUCCESS] SIMREAL DIGITAL TWIN SYSTEM IS ONLINE!             " -ForegroundColor Green
Write-Host "=======================================================================" -ForegroundColor Green
Write-Host " Web Control Center Dashboard : http://localhost:8090" -ForegroundColor Cyan
Write-Host " Spring Boot Actuator Health  : http://localhost:8080/actuator/health" -ForegroundColor White
Write-Host ""
Write-Host " Features:" -ForegroundColor Yellow
Write-Host "   - 100% Zero Terminal Glitches (Visual Web Control Dashboard)" -ForegroundColor Yellow
Write-Host "   - Full 13 Office Zones + Balcony Real-time Telemetry Grid" -ForegroundColor Yellow
Write-Host "   - Visual Switches for Weather, Rain, Lights, AHU, Doors & Windows" -ForegroundColor Yellow
Write-Host ""
Write-Host " Type 'stop' below to safely terminate all background modules & Docker." -ForegroundColor Red
Write-Host "=======================================================================" -ForegroundColor Green

# Master Interactive Control Loop
while ($true) {
    Write-Host -NoNewline "simReal> "
    $input = Read-Host
    if ($input -eq "stop" -or $input -eq "exit" -or $input -eq "quit" -or $input -eq "q") {
        Stop-AllSimReal
        break
    } else {
        Write-Host "Unknown command '$input'. Type 'stop' to shut down all modules." -ForegroundColor Red
    }
}
