import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

# 1. drop orphaned parametrize above deterministic test
start = t.index("def test_frozen_reruns_are_deterministic(")
# find decorator start scanning backwards
dec = t.rfind("@pytest.mark.parametrize", 0, start)
if dec != -1 and t[dec:start].count("\n") <= 8:
    t = t[:dec] + t[start:]

# 2. block-policy escalation: CANON-005 unknown -> error on duplicated/missing
t = t.replace(
    '("duplicated", "fail", "unknown", "fail", "unknown"),',
    '("duplicated", "fail", "error", "fail", "unknown"),',
)
t = t.replace(
    '("missing", "fail", "unknown", "fail", "unknown"),',
    '("missing", "fail", "error", "fail", "unknown"),',
)

# 3. presence test expectation
t = t.replace(
    'assert got["CORE-CANON-005"] == "unknown"                    # presence split pending 001',
    'assert got["CORE-CANON-005"] == "error"                      # block policy escalates; presence split pending 001',
)

ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("patched")
