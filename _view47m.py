import pathlib

p = pathlib.Path(r"D:\projects\externals\agentready-tools\src\agentready\audit_core\link_evaluators.py")
src = p.read_text(encoding="utf-8")
import re

for pat in ("_links_fact(", "_resources_fact(", "EvaluatorRegistry(", "allowlist=", "expected_contracts=", "def _core_link_002", "def _core_link_005"):
    for m in re.finditer(re.escape(pat), src):
        line_no = src[: m.start()].count("\n") + 1
        line = src[m.start() :].splitlines()[0]
        print(f"{line_no}: {line.strip()[:100]}")
