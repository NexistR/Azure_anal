param(
    [string]$PythonExe = '',
    [switch]$InstallDependencies
)
$ErrorActionPreference = 'Stop'
$W2Root = Split-Path -Parent $PSScriptRoot
$ProjectRoot = $W2Root
$RuntimeRoot = Join-Path $W2Root '.runtime\python312'
$VenvRoot = Join-Path $W2Root '.venv'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'
$LegacyPackages = Join-Path $W2Root '.venv\Lib\site-packages'

function Invoke-CheckedPython {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $Executable $Arguments" }
}

if (-not $PythonExe) {
    $LocalRuntime = Join-Path $RuntimeRoot 'python.exe'
    if (Test-Path -LiteralPath $LocalRuntime) {
        $PythonExe = $LocalRuntime
    } else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $PythonCommand) { throw 'Provide a Python 3.12 executable using -PythonExe.' }
        $DetectedVersion = & $PythonCommand.Source -c 'import sys; print("%s.%s" % sys.version_info[:2])'
        if ($DetectedVersion -eq '3.12') {
            $PythonExe = $PythonCommand.Source
        } else {
            $CacheRoot = Join-Path $env:LOCALAPPDATA 'Package Cache'
            $CachedCore = Get-ChildItem -Path (Join-Path $CacheRoot '*v3.12.9150.0\core.msi') -ErrorAction SilentlyContinue
            if (-not $CachedCore) { throw 'Python 3.12 is required. Supply -PythonExe; no download is performed automatically.' }
            Invoke-CheckedPython -Executable $PythonCommand.Source -Arguments @(
                (Join-Path $PSScriptRoot 'recover_cached_python.py'), '--cache', $CacheRoot,
                '--destination', $RuntimeRoot
            )
            $PythonExe = $LocalRuntime
        }
    }
}
Invoke-CheckedPython -Executable $PythonExe -Arguments @('-c', 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 is required"')
Invoke-CheckedPython -Executable $PythonExe -Arguments @('-m', 'venv', '--without-pip', $VenvRoot)

$BridgePath = Join-Path $VenvRoot 'Lib\site-packages\week1_dependencies.pth'
if ($InstallDependencies) {
    # This file was used by an older layout to bridge Week 1 packages.  The
    # integrated project owns this virtual environment, so a self-referencing
    # .pth would only add the same site-packages directory a second time.
    Set-Content -LiteralPath $BridgePath -Encoding ASCII -Value ''
    Invoke-CheckedPython -Executable $VenvPython -Arguments @('-m', 'ensurepip', '--upgrade')
    Invoke-CheckedPython -Executable $VenvPython -Arguments @('-m', 'pip', 'install', '-r', (Join-Path $W2Root 'requirements_w2.txt'))
} else {
    if (-not (Test-Path -LiteralPath $LegacyPackages)) {
        throw 'Week 1 packages are absent. Run again with -InstallDependencies to install requirements_w2.txt.'
    }
    # Keep the legacy marker empty.  Packages are installed directly in this
    # venv; pointing it back to itself creates a recursive/self bridge.
    Set-Content -LiteralPath $BridgePath -Encoding ASCII -Value ''
}

$env:JUPYTER_CONFIG_DIR = Join-Path $W2Root '.cache\jupyter_config'
$env:JUPYTER_DATA_DIR = Join-Path $W2Root '.cache\jupyter_data'
$env:JUPYTER_RUNTIME_DIR = Join-Path $W2Root '.cache\jupyter_runtime'
$env:IPYTHONDIR = Join-Path $W2Root '.cache\ipython'
$env:MPLCONFIGDIR = Join-Path $W2Root '.cache\matplotlib'
Invoke-CheckedPython -Executable $VenvPython -Arguments @((Join-Path $PSScriptRoot 'register_kernel.py'))
Invoke-CheckedPython -Executable $VenvPython -Arguments @((Join-Path $PSScriptRoot 'verify_environment.py'))
Write-Output "Ready: $VenvPython"
Write-Output 'Notebook kernel: azure-w2 (project-local, no global registration)'
