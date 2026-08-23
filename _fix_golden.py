import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")
t = t.replace("_legacy_verdict(scenario).value", "_legacy_verdict(scenario)")

start = t.index("def test_single_collection_no_duplicate_fetch_surface():")
end = t.find("\ndef ", start)
new_test = (
    "def test_single_collection_no_duplicate_fetch_surface():\n"
    '    """Cached bundle identity proves one shared collection per scenario."""\n'
    '    a = _bundles("self-paginated")\n'
    '    b = _bundles("self-paginated")\n'
    "    assert a[0] is b[0] and a[1] is b[1]\n\n\n"
)
# also drop the now-unused legacy_verdict helper wrapper if it only wraps .value
t = (
    t[:start]
    + new_test
    + t[end:].replace(
        "def _legacy_verdict(scenario_name):\n    return _canonical(_corpus(scenario_name)[\"legacy_evidence\"]).status\n",
        "def _legacy_verdict(scenario_name):\n    return str(_canonical(_corpus(scenario_name)[\"legacy_evidence\"]).status)\n",
        1,
    )
)
ast = __import__("ast")
ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("fixed")
