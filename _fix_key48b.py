import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_desc_golden.py"
)
t = p.read_text(encoding="utf-8")
old = 'multi["frozen"]["CORE-CANON-002" if False else "GOOGLE-DESC-001"]'
new = 'multi["frozen"]["GOOGLE-DESC-001"]'
assert old in t, "pattern missing"
t = t.replace(old, new, 1)
ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("key fixed")
