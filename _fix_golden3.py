import ast
import pathlib
import re

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

# A) table corrections
t = t.replace(
    '("duplicated", "fail", "error", "error", "unknown"),',
    '("duplicated", "fail", "error", "fail", "error"),',
)
t = t.replace(
    '("missing", "fail", "error", "error", "unknown"),',
    '("missing", "fail", "error", "fail", "error"),',
)

# B) presence-test expectation
i = t.index("def test_presence_branch_is_blocked_for_replacement():")
j = t.find("\ndef ", i + 1)
seg = t[i : j if j != -1 else len(t)]
seg2 = seg.replace('== "unknown"', '== "error"')
t = t[:i] + seg2 + t[j if j != -1 else len(t) :]

# C) deterministic test: drop orphan decorator directly above it
start = t.index("def test_frozen_reruns_are_deterministic(")
line_start = t.rfind("\n", 0, start) + 1
dec = t.rfind("@pytest.mark.parametrize", 0, line_start)
if dec != -1:
    between = t[dec:start]
    # only strip if nothing but whitespace/newlines/brackets between decorator end and def
    stripped = re.sub(r"@\w+\.mark\.parametrize\(.*?\)\n", "", between, flags=re.S)
    if stripped.strip() == "" or stripped.strip().startswith(("(", '"', "'")) is False and stripped.strip() == "":
        pass
    # safer: rebuild segment without decorator using bracket-aware cut
    dec_end = t.index(")\n", dec) + 2
    between = t[dec_end:start]
    if between.strip() == "":
        t = t[:dec] + t[start:]
        start = None

ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("patched")
