param(
    [Parameter(Position = 0)]
    [ValidateSet('run', 'install-schedule', 'remove-schedule', 'status')]
    [string]$Action = 'run'
)

$ErrorActionPreference = 'Stop'

$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$taskName = 'PersonalTrackerBackup'

function Invoke-Backup {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "Cannot find project Python interpreter: $pythonPath. Run 'uv sync' first."
    }
    Push-Location -LiteralPath $projectRoot
    try {
        & $pythonPath -m scripts.backup_sqlite --keep 30
        $backupExitCode = $LASTEXITCODE
        if ($backupExitCode -ne 0) {
            throw "SQLite backup failed with exit code $backupExitCode."
        }
    }
    finally {
        Pop-Location
    }
}

function Install-BackupSchedule {
    $pwshPath = (Get-Command pwsh -ErrorAction Stop).Source
    $arguments = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "{0}" run' -f $PSCommandPath
    $taskAction = New-ScheduledTaskAction -Execute $pwshPath -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -Daily -At 3:30AM
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Output "Registered $taskName for a daily SQLite backup at 03:30."
}

function Remove-BackupSchedule {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed $taskName backup task."
}

function Show-BackupStatus {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        Write-Output 'PersonalTrackerBackup is not scheduled.'
        return
    }
    $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
    Write-Output "PersonalTrackerBackup is $($task.State). Last run: $($taskInfo.LastRunTime). Result: $($taskInfo.LastTaskResult)."
}

switch ($Action) {
    'run' { Invoke-Backup }
    'install-schedule' { Install-BackupSchedule }
    'remove-schedule' { Remove-BackupSchedule }
    'status' { Show-BackupStatus }
}
