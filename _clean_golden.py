import ast
import pathlib
import re

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

# 1. remove debug probe block
i = t.index("def _dbg_off_origin():")
j = t.index("\ndef ", i + 1)
t = t[:i] + t[j + 1 :]

# 2. unwrap strict-xfail params back to plain tuples
t = re.sub(
    r"pytest\.param\((.*?),\s*marks=pytest\.mark\.xfail\([^)]*\)\),",
    lambda m: m.group(1) + "),",
    t,
    flags=re.S,
)
# fix trailing paren duplication produced by wrap: ')...),' pattern already handled above

ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("probe removed, xfails unwrapped")
