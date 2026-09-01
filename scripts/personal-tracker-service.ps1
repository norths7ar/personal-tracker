param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'logs', 'install-autostart', 'remove-autostart')]
    [string]$Action = 'status'
)

$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$venvBasePython = ''
$venvConfigPath = Join-Path $projectRoot '.venv\pyvenv.cfg'
if (Test-Path -LiteralPath $venvConfigPath) {
    $homeLine = Get-Content -LiteralPath $venvConfigPath -Encoding utf8 |
        Where-Object { $_ -match '^\s*home\s*=\s*(.+)$' } |
        Select-Object -First 1
    if ($homeLine -match '^\s*home\s*=\s*(.+)$') {
        $venvBasePython = [System.IO.Path]::GetFullPath(
            (Join-Path $Matches[1].Trim() 'python.exe')
        )
    }
}
$runtimeDirectory = Join-Path $projectRoot 'data\runtime'
$logDirectory = Join-Path $projectRoot 'data\logs'
$statePath = Join-Path $runtimeDirectory 'personal-tracker.json'
$port = 18080
$healthUri = "http://127.0.0.1:$port/api/health"
$taskName = 'PersonalTrackerLocal'

function Get-ListeningProcessIds {
    $netstatPath = Join-Path $env:SystemRoot 'System32\netstat.exe'
    $lines = & $netstatPath @('-ano', '-p', 'tcp')
    if ($LASTEXITCODE -ne 0) {
        return @()
    }

    $processIds = foreach ($line in $lines) {
        if ($line -notmatch '^\s*TCP\s+(\S+)\s+\S+\s+LISTENING\s+([0-9]+)\s*$') {
            continue
        }
        $localEndpoint = $Matches[1]
        $listeningProcessId = [int]$Matches[2]
        if ($localEndpoint -match ':([0-9]+)$' -and [int]$Matches[1] -eq $port) {
            $listeningProcessId
        }
    }
    return @($processIds | Sort-Object -Unique)
}

function Read-ServiceState {
    if (-not (Test-Path -LiteralPath $statePath)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $statePath -Raw -Encoding utf8 | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Test-Health {
    try {
        $response = Invoke-RestMethod -Uri $healthUri -Method Get -TimeoutSec 2
        return $response.status -eq 'ok'
    }
    catch {
        return $false
    }
}

function Get-ValidatedService {
    $state = Read-ServiceState
    if ($null -eq $state) {
        return $null
    }

    try {
        $process = Get-Process -Id ([int]$state.pid) -ErrorAction Stop
        $actualPython = [System.IO.Path]::GetFullPath($process.Path)
        $expectedPython = [System.IO.Path]::GetFullPath($pythonPath)
        if ($actualPython -ne $expectedPython -and
            (-not $venvBasePython -or $actualPython -ne $venvBasePython)) {
            return $null
        }
        if ((Get-ListeningProcessIds) -notcontains $process.Id -or -not (Test-Health)) {
            return $null
        }
        return [PSCustomObject]@{ Process = $process; State = $state }
    }
    catch {
        return $null
    }
}

function Remove-StaleState {
    if ((Test-Path -LiteralPath $statePath) -and $null -eq (Get-ValidatedService)) {
        Remove-Item -LiteralPath $statePath -Force
    }
}

function Get-RecentLogPaths {
    $state = Read-ServiceState
    if ($null -ne $state -and $state.stdout -and $state.stderr) {
        return [PSCustomObject]@{ Stdout = [string]$state.stdout; Stderr = [string]$state.stderr }
    }
    $stdout = Get-ChildItem -LiteralPath $logDirectory -Filter 'personal-tracker-*.stdout.log' -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $stdout) {
        return $null
    }
    return [PSCustomObject]@{
        Stdout = $stdout.FullName
        Stderr = $stdout.FullName -replace '\.stdout\.log$', '.stderr.log'
    }
}

function Start-Service {
    $managed = Get-ValidatedService
    if ($null -ne $managed) {
        Write-Output "personal-tracker is already running. PID: $($managed.Process.Id). Port: $port."
        return
    }
    $occupied = Get-ListeningProcessIds
    if ($occupied.Count -gt 0) {
        throw "Port $port is occupied by unmanaged PID(s): $($occupied -join ', '). Refusing to start another service."
    }
    Remove-StaleState

    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "Cannot find project Python interpreter: $pythonPath. Run 'uv sync' first."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
        throw "Cannot find frontend build output. Run 'npm run build' in frontend first."
    }

    New-Item -ItemType Directory -Path $runtimeDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $stdoutPath = Join-Path $logDirectory "personal-tracker-$timestamp.stdout.log"
    $stderrPath = Join-Path $logDirectory "personal-tracker-$timestamp.stderr.log"
    $startParameters = @{
        FilePath = $pythonPath
        ArgumentList = @('-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', $port, '--log-level', 'info')
        WorkingDirectory = $projectRoot
        WindowStyle = 'Hidden'
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
        PassThru = $true
    }
    $process = Start-Process @startParameters

    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 250
        $process.Refresh()
        if ($process.HasExited) {
            $stderr = if (Test-Path -LiteralPath $stderrPath) { Get-Content -LiteralPath $stderrPath -Tail 40 -Encoding utf8 } else { @() }
            throw "personal-tracker exited during startup.`n$($stderr -join [Environment]::NewLine)"
        }
        if (Test-Health) {
            $listenerIds = Get-ListeningProcessIds
            if ($listenerIds.Count -ne 1) {
                continue
            }
            $state = [ordered]@{
                pid = $listenerIds[0]
                started_at = (Get-Process -Id $listenerIds[0] -ErrorAction Stop).StartTime.ToUniversalTime().ToString('o')
                python = [System.IO.Path]::GetFullPath($pythonPath)
                port = $port
                stdout = $stdoutPath
                stderr = $stderrPath
            }
            $state | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
            Write-Output "personal-tracker started in background. PID: $($process.Id). Port: $port."
            return
        }
    }

    Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    throw 'personal-tracker did not become healthy and was stopped.'
}

function Stop-Service {
    $managed = Get-ValidatedService
    if ($null -eq $managed) {
        if ((Get-ListeningProcessIds).Count -gt 0) {
            throw "Port $port is occupied, but not by a validated personal-tracker process. Refusing to stop it."
        }
        Remove-StaleState
        Write-Output 'personal-tracker is not running.'
        return
    }
    $processId = [int]$managed.State.pid
    $process = Get-Process -Id $processId -ErrorAction Stop
    $process.Kill()
    if (-not $process.WaitForExit(10000)) {
        throw "personal-tracker did not stop within 10 seconds. PID: $processId."
    }
    Remove-StaleState
    Write-Output "personal-tracker stopped. PID: $processId."
}

function Show-ServiceStatus {
    $managed = Get-ValidatedService
    if ($null -ne $managed) {
        Write-Output "personal-tracker is running. PID: $($managed.Process.Id). Started: $($managed.Process.StartTime). Port: $port."
        return
    }
    if ((Get-ListeningProcessIds).Count -gt 0) {
        Write-Output "Port $port is occupied by unmanaged PID(s): $((Get-ListeningProcessIds) -join ', ')."
        exit 2
    }
    Remove-StaleState
    Write-Output 'personal-tracker is not running.'
    exit 1
}

function Show-ServiceLogs {
    $paths = Get-RecentLogPaths
    if ($null -eq $paths) {
        Write-Output 'No background logs yet.'
        return
    }
    if (Test-Path -LiteralPath $paths.Stdout) {
        Write-Output "=== stdout: $($paths.Stdout) ==="
        Get-Content -LiteralPath $paths.Stdout -Tail 80 -Encoding utf8
    }
    if (Test-Path -LiteralPath $paths.Stderr) {
        Write-Output "=== stderr: $($paths.Stderr) ==="
        Get-Content -LiteralPath $paths.Stderr -Tail 80 -Encoding utf8
    }
}

function Install-Autostart {
    $pwshPath = (Get-Command pwsh -ErrorAction Stop).Source
    $arguments = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" start' -f $PSCommandPath
    $taskAction = New-ScheduledTaskAction -Execute $pwshPath -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Output "Registered $taskName to start personal-tracker at logon."
}

function Remove-Autostart {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed $taskName autostart task."
}

switch ($Action) {
    'start' { Start-Service }
    'stop' { Stop-Service }
    'restart' { Stop-Service; Start-Service }
    'status' { Show-ServiceStatus }
    'logs' { Show-ServiceLogs }
    'install-autostart' { Install-Autostart }
    'remove-autostart' { Remove-Autostart }
}
