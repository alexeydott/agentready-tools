import ast
import pathlib

TS = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_e_wave1_reconciliation.py"
)
t = TS.read_text(encoding="utf-8")

# gate8 tests: forbidden set now excludes resources (produced via Option A)
old_fam = 'families == {"links", "resources", "structured-data"}'
if old_fam in t:
    t = t.replace(old_fam, 'families == {"links", "structured-data"}')

# deferred set expectation: empty after Option A
old_defer = (
    '    assert BASELINE["deferred_declared_not_produced"] == []'
)
if old_defer not in t:
    pass  # freeze file owns this; here we only patch wave1 gates

# non_emitted in manifest handled separately; also update DEFAULT check if present
t = t.replace(
    'assert DEFAULT_FACT_SCHEMA_VERSIONS.get("resources") == "1"\n        assert DEFAULT_FACT_SCHEMA_VERSIONS.get("run-projection")',
    'assert DEFAULT_FACT_SCHEMA_VERSIONS.get("run-projection")',
)

ast.parse(t)
TS.write_text(t, encoding="utf-8", newline="\n")
print("gate8 patched")
