import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def test_portable_packaging_uses_agentready_name_version_info_and_icon():
    spec = (ROOT / "packaging" / "agentready-portable.spec").read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build-portable.ps1").read_text(encoding="utf-8")
    version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")

    assert 'name="agentready"' in spec
    assert 'icon=str(icon_file)' in spec
    assert 'version=str(version_file)' in spec
    assert '$artifact = Join-Path $distRoot "agentready.exe"' in build_script
    assert "OriginalFilename', 'agentready.exe'" in version_info
    assert "FileDescription" in version_info
    assert (ROOT / "packaging" / "agentready.ico").is_file()


def test_portable_packaging_includes_mcp_facade():
    spec = (ROOT / "packaging" / "agentready-portable.spec").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "excludes=[]" in spec.replace(" ", "")
    assert '"agentready.mcp_server"' in spec
    assert 'collect_submodules("mcp")' in spec
    assert '"mcp[cli]>=2,<3"' in pyproject


def test_built_portable_help_includes_examples_for_main_and_nested_modes():
    artifact = ROOT / "dist" / "portable" / "agentready.exe"
    if not artifact.is_file():
        pytest.skip("portable executable has not been built")

    commands = [
        ("--help",),
        ("ai", "credentials", "--help"),
        ("ai", "recommend", "--help"),
        ("ai", "chat", "--help"),
        ("audit", "--mode", "seo", "--help"),
        ("serve", "--help"),
        ("mcp", "--help"),
    ]
    for command in commands:
        result = subprocess.run(
            [str(artifact), *command],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout + result.stderr
        if command[0] == "audit":
            assert "agentready audit" in output
        else:
            assert "Example" in output
            assert output.count("agentready ") >= 2
