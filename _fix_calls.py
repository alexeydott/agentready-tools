import ast
import pathlib
import re

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

pattern = re.compile(r'_bundles\(("[a-z\-]+")\)')
t2, n = pattern.subn(r"_bundles(\1, SCENARIOS[\1])", t)
print("fixed calls:", n)

ast.parse(t2)
p.write_text(t2, encoding="utf-8", newline="\n")
