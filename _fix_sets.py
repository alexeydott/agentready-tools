import ast
import pathlib

TS = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_e_wave1_reconciliation.py"
)
t = TS.read_text(encoding="utf-8")

pairs = [
    (
        'assert families == {"links", "resources", "structured-data"}',
        'assert families == {"links", "structured-data"}',
    ),
    (
        'assert non_emitted == {"links", "resources", "structured-data"}',
        'assert non_emitted == {"links", "structured-data"}',
    ),
]
for old, new in pairs:
    assert old in t, old
    t = t.replace(old, new)

ast.parse(t)
TS.write_text(t, encoding="utf-8", newline="\n")
print("sets fixed")
