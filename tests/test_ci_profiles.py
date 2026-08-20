import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).parents[1]


def test_ci_profiles_install_explicit_dependency_sets_and_isolate_mcp_collection():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release-validation.yml").read_text(encoding="utf-8")

    for workflow in (ci, release):
        assert "actions/checkout@v6" in workflow
        assert "actions/setup-python@v6" in workflow
        assert "actions/checkout@v4" not in workflow
        assert "actions/setup-python@v5" not in workflow

    assert 'python -m pip install -e ".[dev,server]"' in ci
    assert 'python -m pip install -e ".[dev,mcp,server]"' in ci
    assert 'tests/test_acceptance_mcp.py' in ci
    assert 'tests/test_cross_surface_parity.py' in ci
    assert 'python -m pip install -e ".[dev,portable]"' in ci
    assert "--ignore=tests/test_acceptance_mcp.py" in ci
    assert 'python -m pip install -e ".[dev,mcp,portable]"' in release
    assert "python -m build --wheel --sdist" in release
    assert "scripts/package-source.ps1" in release
    assert "python -m venv" in release
    assert 'sha256sum "${wheel}" "${sdist}" "${source_zip}"' in release
    assert "agentready-artifact-sha256.txt" in release
    assert '"${environment}/bin/python" -m pip install "${artifact}[mcp]"' in release
    assert '"${environment}/bin/agentready" mcp --help' in release
    assert 'import agentready.mcp_server' in release
    assert 'test -f "${source_root}/MANIFEST.in"' in release
    assert 'name: Run full suite and report intentional skips' in release
    assert 'python -m pytest -q -ra -m "not scale"' in release
    assert "Unexpected skipped tests in full-release run" not in release
    assert "push:" not in ci and "pull_request:" not in ci
    assert "push:" not in release and "pull_request:" not in release
    assert "workflow_dispatch:" in ci and "workflow_dispatch:" in release

    powershell = (ROOT / "scripts" / "verify-local.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "scripts" / "verify-local.sh").read_text(encoding="utf-8")
    for wrapper in (powershell, shell):
        assert "minimal" in wrapper
        assert "mcp" in wrapper
        assert "browser" in wrapper
        assert "full-nonscale" in wrapper
        assert "sha256" in wrapper.lower()
        assert "clean" in wrapper.lower()

    source_package = (ROOT / "scripts" / "package-source.ps1").read_text(encoding="utf-8")
    assert '"MANIFEST.in"' in source_package
    assert 'pyproject.toml' in source_package
    assert 'Select-String' in source_package
    assert 'Write-Verbose "Included repository-only file: $relative"' in source_package
    assert '[FIX:source-package]' not in source_package
    assert "!tests/fixtures/site_lab/manifest.json" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_mcp_acceptance_module_does_not_import_optional_package_at_collection():
    source = (ROOT / "tests" / "test_acceptance_mcp.py").read_text(encoding="utf-8")
    assert "\nfrom agentready.mcp_server import" not in source
    assert 'pytest.importorskip("mcp")' in source


def test_source_archive_contains_allowlisted_ci_workflows(tmp_path):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("PowerShell is required to execute the source packaging script")

    output = tmp_path / "source.zip"
    subprocess.run(
        [pwsh, "-File", str(ROOT / "scripts" / "package-source.ps1"), "-Output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    with ZipFile(output) as archive:
        names = set(archive.namelist())
    assert ".github/workflows/ci.yml" in names
    assert ".github/workflows/release-validation.yml" in names
    assert not any(name.startswith(".github/skills/") for name in names)
