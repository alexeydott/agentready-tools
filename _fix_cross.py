import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_known_deltas.py"
)
t = p.read_text(encoding="utf-8")

start = t.index("def test_golden_table_marks_every_delta_cell():")
new_test = '''def test_golden_table_marks_every_delta_cell():
    import inspect

    import test_stage_f_canon_golden as g

    src = inspect.getsource(g)
    for key, delta in KNOWN_DELTAS.items():
        assert f"DELTA-{key}" in src, key
        row = next(r for r in g.EXPECTED_TABLE if r[0] == delta["cell"].split(" @ ")[0])
        assert row[1] == "fail", key
'''
t = t[:start] + new_test
ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("cross-test rewritten")
