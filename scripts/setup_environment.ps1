[CmdletBinding()]
param(
    [switch]$IncludeAdvanced,
    [switch]$IncludeSpark
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$jdkHome = Join-Path $projectRoot ".tools\jdk-17"

if (-not (Test-Path -LiteralPath $venvPython)) {
    & py -3.12 -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the Python 3.12 virtual environment" }
}

$pythonVersion = & $venvPython -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
if ($LASTEXITCODE -ne 0 -or $pythonVersion -ne "3.12") {
    throw "This locked environment requires Python 3.12; found $pythonVersion"
}

if ($IncludeSpark) {
    & (Join-Path $PSScriptRoot "install_jdk17.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Failed to install or verify JDK 17" }
    $env:JAVA_HOME = $jdkHome
    $env:PYSPARK_PYTHON = $venvPython
    $env:PYSPARK_DRIVER_PYTHON = $venvPython

    $envFile = Join-Path $projectRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile)) {
        $envContent = @(
            "JAVA_HOME=$jdkHome",
            "PYSPARK_PYTHON=$venvPython",
            "PYSPARK_DRIVER_PYTHON=$venvPython"
        ) -join [Environment]::NewLine
        [IO.File]::WriteAllText(
            $envFile,
            $envContent + [Environment]::NewLine,
            [Text.UTF8Encoding]::new($false)
        )
    }
}

$pipArgs = @(
    "-m", "pip", "install", "--isolated", "--prefer-binary",
    "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple"
)
& $venvPython @pipArgs -r (Join-Path $projectRoot "requirements-core.txt")
if ($LASTEXITCODE -ne 0) { throw "Failed to install the core Python stack" }

if ($IncludeAdvanced) {
    & $venvPython @pipArgs -r (Join-Path $projectRoot "requirements-advanced.txt")
    if ($LASTEXITCODE -ne 0) { throw "Failed to install the advanced Python stack" }
}
if ($IncludeSpark) {
    & $venvPython @pipArgs -r (Join-Path $projectRoot "requirements-optional.txt")
    if ($LASTEXITCODE -ne 0) { throw "Failed to install PySpark" }
}

& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Python dependency validation failed" }
& $venvPython -m ipykernel install --user --name pj-mic --display-name "Python (.venv) - pj_mic"
if ($LASTEXITCODE -ne 0) { throw "Failed to register the Jupyter kernel" }

$checkArgs = @((Join-Path $projectRoot "tools\check_environment.py"))
if ($IncludeAdvanced) { $checkArgs += "--advanced" }
if ($IncludeSpark) { $checkArgs += "--optional" }
& $venvPython @checkArgs
if ($LASTEXITCODE -ne 0) { throw "Python import validation failed" }

$smokeArgs = @((Join-Path $projectRoot "tools\smoke_test_stack.py"))
if ($IncludeAdvanced) { $smokeArgs += "--advanced" }
if ($IncludeSpark) { $smokeArgs += "--spark" }
& $venvPython @smokeArgs
if ($LASTEXITCODE -ne 0) { throw "Functional smoke tests failed" }
