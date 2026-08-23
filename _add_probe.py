import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")
dbg = '''

def _dbg_off_origin():
    sc = "off-origin-single"
    c = _corpus(sc)
    print("PAGE VALUE:", {k: str(v)[:90] for k, v in c["page"].value.items() if k in ("canonicals", "links")})
    print("TRANSPORT :", c["transport"].value)
    r2 = evaluate_canon_rule("CORE-CANON-002", TARGET, _bundles(sc))
    f = r2.finding
    import dataclasses as _dc

    print("002:", f.status.value, "|", getattr(f, "reason", "") if hasattr(f, "reason") else "", )
    for fld in _dc.fields(f):
        v = str(getattr(f, fld.name))[:120]
        print("   ", fld.name, "=", v)


def test_dbg_off_origin_probe():
    _dbg_off_origin()
'''
anchor = "# ---------------------------------------------------------------------------\n# classification table"
t = t.replace(anchor, dbg.strip("\n") + "\n\n\n" + anchor, 1)
ast = __import__("ast")
ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("debug probe added")
