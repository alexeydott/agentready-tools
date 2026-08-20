[CmdletBinding()]
param(
    [switch]$AllowDirty,
    [switch]$SkipBrowserInstall,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    $sha = (git rev-parse HEAD).Trim()
    $status = (git status --porcelain)
    if ($status -and -not $AllowDirty) {
        throw "Working tree is dirty. Commit or rerun with -AllowDirty; dirty runs are not merge-gate evidence."
    }
    $version = (& $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
    $runId = Get-Date -Format "yyyyMMdd-HHmmss"
    $reportDir = Join-Path $root "dist\local-verification"
    New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
    $reportPath = Join-Path $reportDir "verification-$sha-$runId.json"
    $results = [ordered]@{
        commit = $sha
        dirty = [bool]$status
        package_version = $version
        python = (& $Python --version).Trim()
        os = [System.Environment]::OSVersion.VersionString
        playwright = (& $Python -c "import importlib.metadata as m; print(m.version('playwright'))").Trim()
        chromium_cache = (Join-Path $HOME ".cache\ms-playwright")
        started_at = (Get-Date).ToUniversalTime().ToString("o")
        profiles = [ordered]@{}
        artifacts = @()
    }

    function Run-Profile([string]$Name, [string[]]$Arguments) {
        $output = Join-Path $reportDir "$runId-$Name.txt"
        Write-Host "[$Name] $Python $($Arguments -join ' ')"
        & $Python @Arguments 2>&1 | Tee-Object -FilePath $output
        $exitCode = $LASTEXITCODE
        $summary = ((Get-Content -LiteralPath $output -Raw) -split "\r?\n" |
            Where-Object { $_ -match "\d+ passed|\d+ failed|\d+ skipped|\d+ xfailed" } |
            Select-Object -Last 1)
        $results.profiles[$Name] = [ordered]@{ exit_code = $exitCode; summary = $summary }
        if ($exitCode -ne 0) { throw "Profile '$Name' failed with exit code $exitCode." }
    }

    & $Python -m pip install -e ".[dev,server]"
    Run-Profile "minimal" @("-m","pytest","-q","-ra","-m","not scale","--ignore=tests/test_acceptance_mcp.py")
    & $Python -m pip install -e ".[dev,mcp,server]"
    Run-Profile "mcp" @("-m","pytest","-q","-ra","tests/test_acceptance_mcp.py","tests/test_agentfindings.py","tests/test_cli.py","tests/test_mobile.py","tests/test_cross_surface_parity.py")
    & $Python -m pip install -e ".[dev,portable]"
    if (-not $SkipBrowserInstall) { & $Python -m playwright install chromium }
    Run-Profile "browser" @("-m","pytest","-q","-ra","tests/test_acceptance_matrix.py","tests/test_collection_boundaries.py","tests/test_mobile.py")
    & $Python -m pip install -e ".[dev,mcp,portable]"
    Run-Profile "full-nonscale" @("-m","pytest","-q","-ra","-m","not scale")

    $artifactDir = Join-Path $reportDir "$runId-artifacts"
    New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
    & $Python -m pip install --upgrade build
    & $Python -m build --wheel --sdist --outdir $artifactDir
    & pwsh -NoProfile -File (Join-Path $root "scripts\package-source.ps1") -Output (Join-Path $artifactDir "agentready-tools-$version-source.zip")
    $archives = @(Get-ChildItem -LiteralPath $artifactDir -File)
    foreach ($archive in $archives) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive.FullName).Hash.ToLowerInvariant()
        $results.artifacts += [ordered]@{ name = $archive.Name; sha256 = $hash }
    }
    $results.artifact_inspection = "passed"
    foreach ($archive in $archives) {
        if ($archive.Extension -eq ".whl" -or $archive.Extension -eq ".zip" -or $archive.Name.EndsWith(".tar.gz")) {
            & $Python -c "import sys, tarfile, zipfile; p=sys.argv[1]; n=tarfile.open(p).getnames() if p.endswith('.tar.gz') else zipfile.ZipFile(p).namelist(); forbidden={'.ai-factory','.agents','.codex','.agentready.yml','.git'}; assert not any(x in forbidden for y in n for x in y.replace('\\','/').split('/')); assert any(y.endswith('schemas/agentready.audit.v2.schema.json') for y in n)" $archive.FullName
        }
    }
    $smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("agentready-smoke-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null
    try {
        foreach ($archive in $archives | Where-Object { $_.Extension -in @(".whl", ".gz", ".zip") }) {
            $envPath = Join-Path $smokeRoot $archive.BaseName.Replace(".", "-")
            & $Python -m venv $envPath
            $venvPython = Join-Path $envPath "Scripts\python.exe"
            & $venvPython -m pip install --upgrade pip
            if ($archive.Extension -eq ".zip") {
                $sourceRoot = Join-Path $smokeRoot "source"
                Expand-Archive -LiteralPath $archive.FullName -DestinationPath $sourceRoot
                & $venvPython -m pip install "$sourceRoot[mcp]"
            } else {
                & $venvPython -m pip install "$($archive.FullName)[mcp]"
            }
            & (Join-Path $envPath "Scripts\agentready.exe") --help
            & (Join-Path $envPath "Scripts\agentready.exe") mcp --help
            & $venvPython -c "import agentready.mcp_server"
        }
    }
    finally {
        if (Test-Path -LiteralPath $smokeRoot) { Remove-Item -LiteralPath $smokeRoot -Recurse -Force }
    }
    $results.clean_install_smoke = "passed"
    $results.finished_at = (Get-Date).ToUniversalTime().ToString("o")
    $results | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportPath -Encoding utf8
    Write-Host "Local verification passed. Report: $reportPath"
}
finally {
    Pop-Location
}
