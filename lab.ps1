param(
    [ValidateSet('build', 'test', 'doctor', 'clean', 'unit')]
    [string]$Action = 'test',
    [ValidateSet('full', 'quick', 'spice', 'software', 'simulation')]
    [string]$Profile = 'full',
    [switch]$Apply,
    [switch]$All
)
$ErrorActionPreference = 'Stop'
$env:PYTHONDONTWRITEBYTECODE = '1'
$launcherArgs = @((Join-Path $PSScriptRoot 'environment\host.py'), $Action, '--profile', $Profile)
if ($Apply) { $launcherArgs += '--apply' }
if ($All) { $launcherArgs += '--all' }
& python @launcherArgs
exit $LASTEXITCODE
