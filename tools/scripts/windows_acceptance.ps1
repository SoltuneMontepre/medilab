<#
Runs the Windows setup acceptance collector from this checkout.
Doctor is read-only. -RunSetup explicitly initializes a separate empty linked worktree.
#>
[CmdletBinding()]
param([switch]$RunSetup)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$failureReason = 'Native Python 3.12 or the collector could not return valid evidence.'
try {
    $python = (Get-Command python.exe -CommandType Application -ErrorAction Stop).Source
    if ($python -match '(?i)[\\/]Microsoft[\\/]WindowsApps[\\/]python(?:\.exe)?$') {
        $failureReason = 'Disable the Python Store execution alias and select native Python 3.12 or newer.'
        throw 'Python execution alias refused.'
    }
    $collector = Join-Path $PSScriptRoot 'windows_acceptance.py'
    $arguments = @('-B', '-X', 'utf8', $collector, '--shell-version', $PSVersionTable.PSVersion.ToString())
    if ($RunSetup) {
        $arguments += '--run-setup'
    }
    $output = & $python @arguments
    $code = $LASTEXITCODE
    $evidence = ($output | Out-String) | ConvertFrom-Json -ErrorAction Stop
    $evidence | ConvertTo-Json -Depth 20 -Compress
    exit $code
}
catch {
    [pscustomobject]@{
        schema_version = 1
        mode = $(if ($RunSetup) { 'run_setup' } else { 'doctor' })
        status = 'blocked'
        acceptance = 'unverified'
        reason = $failureReason
    } | ConvertTo-Json -Compress
    exit 2
}
