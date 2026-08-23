import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

NL = chr(10)
old1 = '_bundles("self-paginated", SCENARIOS["self-paginated"])'
new1 = '_bundles("self-paginated", _sc("self-paginated"))'
old2 = '_bundles("off-origin-single", SCENARIOS["off-origin-single"])'
new2 = '_bundles("off-origin-single", _sc("off-origin-single"))'

t = t.replace(old1, new1).replace(old2, new2)

helper = (
    "\n\ndef _sc(name):\n"
    '    doc = yaml.safe_load((REPO_ROOT / MANIFEST).read_text(encoding="utf-8"))\n'
    '    return next(s for s in doc["scenarios"] if s["name"] == name)\n'
)
anchor = "def _legacy_verdict_for(corpus):"
if "_sc(name)" not in t:
    i = t.index(anchor)
    t = t[:i] + helper + "\n\n" + t[i:]

ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("wired")
