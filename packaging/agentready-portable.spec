from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPECPATH).resolve().parent
src_root = project_root / "src"
sys.path.insert(0, str(src_root))
version = __import__("agentready").__version__
version_file = project_root / "packaging" / "version_info.txt"
icon_file = project_root / "packaging" / "agentready.ico"

hiddenimports = [
    *collect_submodules("fastapi"),
    *collect_submodules("uvicorn"),
    *collect_submodules("google.auth"),
    *collect_submodules("google.oauth2"),
    *collect_submodules("google.auth.transport"),
    *collect_submodules("google.analytics.data_v1beta"),
    *collect_submodules("googleapiclient"),
    *collect_submodules("mcp"),
    *collect_submodules("playwright"),
    *collect_submodules("openai"),
    *collect_submodules("keyring"),
    "agentready.mcp_server",
    "agentready.mobile_render",
]

datas = [
    *collect_data_files("certifi"),
]

# Explicitly add agentready package data files
catalog_dir = src_root / "agentready" / "seo" / "rules" / "catalog"
for f in catalog_dir.glob("*.yaml"):
    datas.append((str(f), f"agentready/seo/rules/catalog"))
for f in catalog_dir.glob("*.json"):
    datas.append((str(f), f"agentready/seo/rules/catalog"))

a = Analysis(
    [str(project_root / "packaging" / "portable_entrypoint.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="agentready",
    icon=str(icon_file),
    version=str(version_file),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
