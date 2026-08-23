import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

anchor = '    "paginated-other-final": {'
add = (
    '    "paginated-canonical-drift": {\n'
    '        "canonicals": [FINAL],\n'
    '        "links": [_row(0, "/next", f"{ORIGIN_TEST}/next", "next")],\n'
    '        "final_url": OTHER_PATH,\n'
    "    },\n"
)
assert anchor in t and '"paginated-canonical-drift": {' not in t
t = t.replace(anchor, add + anchor, 1)

t = t.replace(
    "def test_frozen_reruns_are_deterministic(scenario):",
    "def test_frozen_reruns_are_deterministic():",
    1,
)
ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("fixed scenario + signature")
