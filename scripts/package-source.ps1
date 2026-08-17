[CmdletBinding()]
param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$version = & python -c "from agentready import __version__; print(__version__)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
    throw "Unable to read package version. Activate the project virtual environment first."
}

if ([string]::IsNullOrWhiteSpace($Output)) {
    $Output = Join-Path $projectRoot "dist\source\agentready-tools-$($version.Trim())-source.zip"
}

$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("agentready-source-" + [guid]::NewGuid().ToString("N"))
$rootName = "agentready-tools-$($version.Trim())"
$stageRoot = Join-Path $stage $rootName

try {
    New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null
    # .agentready.yml is a machine-local configuration artifact. It must stay
    # available in a developer checkout but must never enter a source archive.
    $files = @(
        ".gitignore", "CHANGELOG.md", "LICENSE", "NOTICE.md",
        "README.md", "pyproject.toml", "requirements.txt", "requirements-dev.txt"
    )
    $directories = @("docs", "packaging", "schemas", "scripts", "src", "tests")
    $excludedDocumentationDirectories = @("presentations", "vNext")
    $requiredSchemaFiles = @(
        "agentready.ai-assistant.v2.schema.json",
        "agentready.audit.v2.schema.json",
        "agentready.findings.v2.schema.json",
        "agentready.mobile.v2.schema.json",
        "agentready.protocol-findings.v2.schema.json",
        "agentready.remediation-plan.v2.schema.json",
        "agentready.seo.v2.schema.json"
    )

    foreach ($relative in $files) {
        $source = Join-Path $projectRoot $relative
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            $destination = Join-Path $stageRoot $relative
            New-Item -ItemType Directory -Force -Path (Split-Path $destination) | Out-Null
            Copy-Item -LiteralPath $source -Destination $destination
        }
    }
    foreach ($relative in $directories) {
        $source = Join-Path $projectRoot $relative
        if (Test-Path -LiteralPath $source -PathType Container) {
            Copy-Item -LiteralPath $source -Destination $stageRoot -Recurse
        }
    }
    Get-ChildItem -LiteralPath $stageRoot -Recurse -Directory |
        Where-Object { $_.Name.StartsWith(".") } |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force
    foreach ($relative in $excludedDocumentationDirectories) {
        $excludedPath = Join-Path $stageRoot "docs\$relative"
        if (Test-Path -LiteralPath $excludedPath) {
            Remove-Item -LiteralPath $excludedPath -Recurse -Force
        }
    }

    foreach ($schemaFile in $requiredSchemaFiles) {
        $schemaPath = Join-Path $stageRoot "schemas\$schemaFile"
        if (-not (Test-Path -LiteralPath $schemaPath -PathType Leaf)) {
            throw "Required product schema is missing from the source package: $schemaFile"
        }
    }

    Get-ChildItem -LiteralPath $stageRoot -Recurse -Directory |
        Where-Object { $_.Name -eq "__pycache__" -or $_.Name -like "*.egg-info" } |
        Sort-Object FullName -Descending |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath $stageRoot -Recurse -File |
        Where-Object { $_.Extension -in @(".pyc", ".pyo") } |
        Remove-Item -Force

    $forbiddenNames = @(".agentready.yml", ".ai-factory", ".agents", ".codex")
    $forbiddenEntries = Get-ChildItem -LiteralPath $stageRoot -Recurse -Force |
        Where-Object { $_.Name -in $forbiddenNames }
    if ($forbiddenEntries) {
        $names = ($forbiddenEntries | ForEach-Object FullName) -join ", "
        throw "Source package contains forbidden local artifacts: $names"
    }

    $outputDirectory = Split-Path $Output
    New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
    if (Test-Path -LiteralPath $Output) {
        Remove-Item -LiteralPath $Output -Force
    }
    Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $Output -CompressionLevel Optimal
    Write-Host "Source archive created: $Output"
}
finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
