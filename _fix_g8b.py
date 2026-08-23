import ast
import pathlib

TS = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_e_wave1_reconciliation.py"
)
t = TS.read_text(encoding="utf-8")

# 1) manifest YAML: resources moved out of non_emitted; adapter entry added
MP = pathlib.Path(
    r"D:\projects\externals\agentready-tools\docs\stage-e-wave1-reconciliation.yaml"
)
m = MP.read_text(encoding="utf-8")
m = m.replace(
    "non_emitted_registered_families: [links, structured-data]",
    "non_emitted_registered_families: [links, structured-data]",
)

old_emitters_tail = (
    "    - family: run-projection\n"
    "      adapter: >\n"
    "        audit_core.collection resource_fact_envelope /\n"
    "        canonical_projection_fact_envelopes"
)
# add resources emitter after run-projection block if absent
if "- family: representation" in m and "- family: resources" not in m:
    rep_block = (
        "    - family: representation\n"
        "      adapter: audit_core.collection replay_collected_pages surfacing SiteStore page records (status_code/content_type) alongside parsed payloads"
    )
    new_rep = (
        rep_block
        + "\n"
        + "    - family: resources\n"
        + "      adapter: >\n"
        + "        audit_core.collection resource_fact_envelope / "
        + "load_resources_fact_envelopes \u2014 produced per Option A\n"
    )
    m = m.replace(rep_block, new_rep, 1)

ast.parse(m) if False else None
import yaml as _yaml  # noqa: E402

_yaml.safe_load(m)
MP.write_text(m, encoding="utf-8", newline="\n")
print("manifest updated")

# 2) test expectations for non-emitted set and emitters set
start = t.index("def test_gate8_pipeline_modules_never_construct_non_emitted_family_envelopes")
end = t.find("\ndef ", start + 10)
seg = t[start:end]
seg = seg.replace(
    'families = {"links", "structured-data"}',
    'families = {"links", "structured-data"}',
)
new_test = seg.replace(
    'assert families == {"links", "structured-data"}',
    'assert families == {"links", "structured-data"}',
)
t = t[:start] + new_test + t[end:]

ast.parse(t)
TS.write_text(t, encoding="utf-8", newline="\n")
print("gate tests updated")
