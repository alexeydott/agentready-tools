[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildRoot = Join-Path $projectRoot "build\portable"
$distRoot = Join-Path $projectRoot "dist\portable"
$specPath = Join-Path $projectRoot "packaging\agentready-portable.spec"

function Write-BuildLog {
    param(
        [ValidateSet("INFO", "DEBUG", "ERROR")]
        [string]$Level,
        [string]$Message
    )
    Write-Host "$Level [portable-build] $Message"
}

Write-BuildLog INFO "Starting native Win64 portable build."

if ($env:OS -ne "Windows_NT") {
    throw "Portable Win64 build requires Windows_NT."
}

$pythonBits = & python -c "import struct; print(struct.calcsize('P') * 8)"
if ($LASTEXITCODE -ne 0 -or $pythonBits.Trim() -ne "64") {
    throw "Portable Win64 build requires a 64-bit Python interpreter."
}

$version = & python -c "from agentready import __version__; print(__version__)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
    throw "Unable to read agentready package version."
}

if (-not (Test-Path -LiteralPath $specPath -PathType Leaf)) {
    throw "PyInstaller spec not found: $specPath"
}

$requiredImports = @(
    "httpx", "dns", "yaml", "fastapi", "uvicorn", "google.auth",
    "google.analytics.data_v1beta", "googleapiclient", "mcp",
    "playwright", "openai", "keyring"
)
foreach ($module in $requiredImports) {
    & python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$module') else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "Missing portable dependency '$module'. Install requirements-dev.txt before building."
    }
}

if ($Clean) {
    foreach ($path in @($buildRoot, $distRoot)) {
        if (Test-Path -LiteralPath $path) {
            Write-BuildLog DEBUG "Removing explicit build path: $path"
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
}

New-Item -ItemType Directory -Force -Path $buildRoot, $distRoot | Out-Null
Write-BuildLog INFO "Building version $version into $distRoot."
Write-BuildLog DEBUG "Using spec: $specPath"

& python -m PyInstaller `
    --clean `
    --noconfirm `
    --distpath $distRoot `
    --workpath $buildRoot `
    $specPath

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$artifact = Join-Path $distRoot "agentready.exe"
if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
    throw "Expected standalone portable executable was not created: $artifact"
}

Write-BuildLog INFO "Portable one-file build completed: $artifact"
