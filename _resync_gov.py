import hashlib
import pathlib
import re
import sys

sys.path.insert(0, "src")

import yaml  # noqa: E402

CAT = pathlib.Path("src/agentready/seo/rules/catalog/agentready.rule-catalog.v2.yaml")
DIGEST = hashlib.sha256(CAT.read_bytes()).hexdigest()

SEM = pathlib.Path("src/agentready/seo/rules/catalog/agentready.rule-semantics.v2.yaml")
s = SEM.read_text(encoding="utf-8")
s = re.sub(r"version: 2\.1\.0-draft\.\d+", f"version: {yaml.safe_load(CAT.read_text(encoding='utf-8'))['catalog_version']}", s)
s = re.sub(r"digest: [0-9a-f]{64}", f"digest: {DIGEST}", s, count=1)
# amendments: LINK-001/004 -> page+representation
doc = yaml.safe_load(s)
for a in doc["requirement_amendments"]:
    if a["rule_id"] in {"CORE-LINK-001", "CORE-LINK-004"}:
        a["families"] = ["page", "representation"]
s = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
SEM.write_text(s, encoding="utf-8", newline="\n")

MX = pathlib.Path("docs/stage-e-wave1-reconciliation.yaml")
mxt = MX.read_text(encoding="utf-8")
mxt = re.sub(r"(name: agentready.rule-catalog.v2\n\s*version: )[^\n]+", r"\g<1>" + yaml.safe_load(CAT.read_text(encoding='utf-8'))['catalog_version'], mxt)
mxt = re.sub(r"digest: [0-9a-f]{64}", f"digest: {DIGEST}", mxt, count=1)
MX.write_text(mxt, encoding="utf-8", newline="\n")

from agentready.seo.stage_e_reconciliation import build_stage_e_reconciliation_matrix  # noqa: E402
from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot  # noqa: E402

snap = load_rule_catalog_snapshot()
pathlib.Path("docs/stage-e-f-reconciliation.yaml").write_text(
    yaml.safe_dump(build_stage_e_reconciliation_matrix(snap), sort_keys=False, allow_unicode=True),
    encoding="utf-8", newline="\n",
)
print("catalog:", snap.catalog_version, snap.rule_catalog_digest[:12])
