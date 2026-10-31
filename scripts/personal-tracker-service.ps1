#Requires -Version 7.4
<#
.SYNOPSIS
Project-owned local service lifecycle. External managers call this script only.
.DESCRIPTION
status always returns JSON. start/stop/restart accept -Json for machine output.
Use the same -DataPath and -Port for every operation on an isolated instance.
No automatic startup, scheduled task, backup job or extra manager service.
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'status')]
    [string]$Action = 'status',
    [string]$DataPath,
    [ValidateRange(1, 65535)]
    [int]$Port = 18080,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
$dataDirectory = if ($DataPath) { [IO.Path]::GetFullPath($DataPath) } else { Join-Path $projectRoot 'data' }
if (-not (Test-Path -LiteralPath $pythonPath)) {
    [Console]::Error.WriteLine("Project Python is missing. Run 'uv sync' in the project first.")
    exit 1
}
$nativeArgs = @(
    '-m', 'scripts.service_manager', $Action.ToLowerInvariant(),
    '--data-path', $dataDirectory, '--port', [string]$Port
)
if ($Json) { $nativeArgs += '--json' }
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath @nativeArgs
    $resultCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $resultCode
