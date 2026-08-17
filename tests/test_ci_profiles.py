from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_ci_profiles_install_explicit_dependency_sets_and_isolate_mcp_collection():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release-validation.yml").read_text(encoding="utf-8")

    assert 'python -m pip install -e ".[dev]"' in ci
    assert 'python -m pip install -e ".[dev,mcp]"' in ci
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
    assert "Unexpected skipped tests in full-release run" in release

    source_package = (ROOT / "scripts" / "package-source.ps1").read_text(encoding="utf-8")
    assert '"MANIFEST.in"' in source_package


def test_mcp_acceptance_module_does_not_import_optional_package_at_collection():
    source = (ROOT / "tests" / "test_acceptance_mcp.py").read_text(encoding="utf-8")
    assert "\nfrom agentready.mcp_server import" not in source
    assert 'pytest.importorskip("mcp")' in source
