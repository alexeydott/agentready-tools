import pathlib
import sys

sys.path.insert(0, "src")

import yaml  # noqa: E402

W1 = pathlib.Path("docs/stage-e-wave1-reconciliation.yaml")
EF = pathlib.Path("docs/stage-e-f-reconciliation.yaml")

t = W1.read_text(encoding="utf-8")

old_ne = (
    "non_emitted_registered_families:\n"
    "  - links\n"
    "  - resources\n"
    "  - structured-data\n"
)
new_ne = (
    "non_emitted_registered_families:\n"
    "  - links\n"
    "  - structured-data\n"
)
assert old_ne in t, "non_emitted block not found"
t = t.replace(old_ne, new_ne, 1)

rep_anchor = (
    "    - family: representation\n"
    "      adapter: audit_core.collection replay_collected_pages surfacing "
    "SiteStore page records (status_code/content_type) alongside parsed payloads"
)
res_block = (
    rep_anchor
    + "\n"
    + "    - family: resources\n"
    + "      adapter: >\n"
    + "        audit_core.collection resource_fact_envelope /\n"
    + "        load_resources_fact_envelopes \u2014 produced per Option A\n"
)
if "- family: resources\n" not in t.split("scenarios:")[0]:
    assert rep_anchor in t, "representation emitter anchor not found"
    t = t.replace(rep_anchor, res_block, 1)

W1.write_text(t, encoding="utf-8", newline="\n")

from agentready.audit_core.rule_catalog import load_rule_catalog_snapshot  # noqa: E402
from agentready.seo.stage_e_reconciliation import (  # noqa: E402
    build_stage_e_reconciliation_matrix,
)

snap = load_rule_catalog_snapshot()
EF.write_text(
    yaml.safe_dump(
        build_stage_e_reconciliation_matrix(snap),
        sort_keys=False,
        allow_unicode=True,
    ),
    encoding="utf-8",
    newline="\n",
)

chk = yaml.safe_load(W1.read_text(encoding="utf-8"))
print("non_emitted:", chk["adapter_boundary"]["non_emitted_registered_families"])
print("emitter families:", sorted(e["family"] for e in chk["adapter_boundary"]["emitters"]))
