#!/usr/bin/env bash
set -euo pipefail

allow_dirty=0
skip_browser_install=0
for arg in "$@"; do
  case "$arg" in
    --allow-dirty) allow_dirty=1 ;;
    --skip-browser-install) skip_browser_install=1 ;;
    *) echo "Usage: $0 [--allow-dirty] [--skip-browser-install]" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
sha="$(git rev-parse HEAD)"
dirty="$(test -n "$(git status --porcelain)" && echo true || echo false)"
if [[ "$dirty" == true && "$allow_dirty" != 1 ]]; then
  echo "Working tree is dirty. Commit or rerun with --allow-dirty." >&2
  exit 1
fi
python_bin="${PYTHON:-python3}"
version="$("$python_bin" -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
run_id="$(date -u +%Y%m%d-%H%M%S)"
report_dir="$root/dist/local-verification"
artifact_dir="$report_dir/${run_id}-artifacts"
mkdir -p "$artifact_dir"
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
declare -a profile_names=()
declare -a profile_results=()
run_profile() {
  local name="$1"; shift
  profile_names+=("$name")
  echo "[$name] $python_bin $*"
  set +e
  "$python_bin" "$@" 2>&1 | tee "$report_dir/${run_id}-${name}.txt"
  local code=${PIPESTATUS[0]}
  set -e
  profile_results+=("$name:$code")
  return "$code"
}
mkdir -p "$report_dir"
"$python_bin" -m pip install -e '.[dev,server]'
run_profile minimal -m pytest -q -ra -m 'not scale' --ignore=tests/test_acceptance_mcp.py
"$python_bin" -m pip install -e '.[dev,mcp,server]'
run_profile mcp -m pytest -q -ra tests/test_acceptance_mcp.py tests/test_agentfindings.py tests/test_cli.py tests/test_mobile.py tests/test_cross_surface_parity.py
"$python_bin" -m pip install -e '.[dev,portable]'
if [[ "$skip_browser_install" != 1 ]]; then "$python_bin" -m playwright install chromium; fi
run_profile browser -m pytest -q -ra tests/test_acceptance_matrix.py tests/test_collection_boundaries.py tests/test_mobile.py
"$python_bin" -m pip install -e '.[dev,mcp,portable]'
run_profile full-nonscale -m pytest -q -ra -m 'not scale'
"$python_bin" -m pip install --upgrade build
"$python_bin" -m build --wheel --sdist --outdir "$artifact_dir"
command -v pwsh >/dev/null || { echo "pwsh is required for the allowlisted source archive." >&2; exit 1; }
pwsh -NoProfile -File "$root/scripts/package-source.ps1" -Output "$artifact_dir/agentready-tools-${version}-source.zip"
ARTIFACT_DIR="$artifact_dir" "$python_bin" -c 'import os, tarfile, zipfile; from pathlib import Path; p=Path(os.environ["ARTIFACT_DIR"]); forbidden={".ai-factory",".agents",".codex",".agentready.yml",".git"}; archives=[x for x in p.iterdir() if x.name.endswith((".whl",".tar.gz",".zip"))]; assert archives; assert all(not any(part in forbidden for name in (tarfile.open(x).getnames() if x.name.endswith(".tar.gz") else zipfile.ZipFile(x).namelist()) for part in Path(name).parts) for x in archives); source=[x for x in archives if x.name.endswith("-source.zip")]; assert source and all(any(name.endswith("schemas/agentready.audit.v2.schema.json") for name in zipfile.ZipFile(x).namelist()) for x in source)'
smoke_root="$(mktemp -d)"
trap 'rm -rf "$smoke_root"' EXIT
for artifact in "$artifact_dir"/*.whl "$artifact_dir"/*.tar.gz; do
  env_dir="$smoke_root/$(basename "$artifact" | tr '.+' '--')"
  "$python_bin" -m venv "$env_dir"
  "$env_dir/bin/python" -m pip install --upgrade pip
  "$env_dir/bin/python" -m pip install "${artifact}[mcp]"
  "$env_dir/bin/agentready" --help
  "$env_dir/bin/agentready" mcp --help
  "$env_dir/bin/python" -c 'import agentready.mcp_server'
done
source_root="$smoke_root/source"
mkdir -p "$source_root"
"$python_bin" -m zipfile -e "$artifact_dir/agentready-tools-${version}-source.zip" "$source_root"
"$python_bin" -m venv "$smoke_root/source-venv"
"$smoke_root/source-venv/bin/python" -m pip install --upgrade pip
"$smoke_root/source-venv/bin/python" -m pip install "${source_root}[mcp]"
"$smoke_root/source-venv/bin/agentready" --help
"$smoke_root/source-venv/bin/agentready" mcp --help
"$smoke_root/source-venv/bin/python" -c 'import agentready.mcp_server'
report_path="$report_dir/verification-${sha}-${run_id}.json"
profiles="$(printf '%s\n' "${profile_results[@]}")"
python_bin="$python_bin" artifact_dir="$artifact_dir" dirty="$dirty" profiles="$profiles" started_at="$started_at" report_path="$report_path" "$python_bin" -c 'import hashlib, importlib.metadata, json, os, platform, subprocess, sys, time, tomllib; from pathlib import Path; p=Path(os.environ["artifact_dir"]); a=[{"name":x.name,"sha256":hashlib.sha256(x.read_bytes()).hexdigest()} for x in p.iterdir() if x.is_file()]; out={"commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"dirty":os.environ["dirty"]=="true","package_version":tomllib.load(open("pyproject.toml","rb"))["project"]["version"],"python":sys.version,"os":platform.platform(),"playwright":importlib.metadata.version("playwright"),"chromium_cache":str(Path.home()/".cache"/"ms-playwright"),"profiles":os.environ["profiles"].splitlines(),"artifacts":a,"artifact_inspection":"passed","clean_install_smoke":"passed","started_at":os.environ["started_at"],"finished_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}; Path(os.environ["report_path"]).write_text(json.dumps(out,indent=2),encoding="utf-8")'
echo "Local verification passed. Report: $report_dir/verification-${sha}-${run_id}.json"
