import ast
import pathlib
import re

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

start = t.index("EXPECTED_TABLE = [")
end = t.index("]", start) + 1

NEW = '''EXPECTED_TABLE = [
    ("self-non-paginated", "pass", "pass", "pass", "pass"),
    ("self-paginated", "pass", "pass", "pass", "pass"),
    ("off-origin-single", "fail", "pass", "pass", "fail"),
    ("self-host-other-path-single", "fail", "pass", "pass", "pass"),
    ("paginated-other-final", "pass", "pass", "pass", "pass"),
    ("paginated-canonical-drift", "fail", "fail", "pass", "pass"),
    ("duplicated", "fail", "error", "fail", "error"),
    ("missing", "fail", "error", "fail", "error"),
]'''
t = t[:start] + NEW + t[end:]

ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("table rebuilt")
