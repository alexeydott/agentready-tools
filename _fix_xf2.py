import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

a = (
    '    ("duplicated", "fail", "error", "fail", "error"),' + "\n"
    '    ("missing", "fail", "error", "fail", "error"),'
)
xf_a = (
    "    pytest.param(\n"
    '        "duplicated", "fail", "error", "fail", "error",\n'
    '        marks=pytest.mark.xfail(\n'
    '            reason="#34: escalation nondeterminism under investigation",\n'
    '            strict=True,\n'
    "        ),\n"
    "    ),\n"
)
xf_b = (
    "    pytest.param(\n"
    '        "missing", "fail", "error", "fail", "error",\n'
    '        marks=pytest.mark.xfail(\n'
    '            reason="#34: escalation nondeterminism under investigation",\n'
    '            strict=True,\n'
    "        ),\n"
    "    ),\n"
)
assert a in t
t = t.replace(a, xf_a + xf_b, 1)

ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("xfails added")
