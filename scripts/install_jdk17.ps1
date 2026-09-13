[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $projectRoot ".tools\jdk-17"
$archive = Join-Path $env:TEMP "OpenJDK17U-jdk_x64_windows_hotspot_17.0.20.1_1.zip"
$url = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_windows_hotspot_17.0.20.1_1.zip"
$expectedSha256 = "e53a79c3c3d86865bd7e787903884331068e71321714ffd44f145785affc7cb0"

if (-not (Test-Path -LiteralPath (Join-Path $target "bin\java.exe"))) {
    curl.exe -fL --retry 3 --retry-delay 2 -o $archive $url
    if ($LASTEXITCODE -ne 0) { throw "JDK download failed" }
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expectedSha256) { throw "JDK checksum mismatch" }
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    tar.exe -xf $archive -C $target --strip-components 1
    if ($LASTEXITCODE -ne 0) { throw "JDK extraction failed" }
}

& (Join-Path $target "bin\java.exe") -version
