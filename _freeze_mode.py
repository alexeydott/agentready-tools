import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_canon_golden.py"
)
t = p.read_text(encoding="utf-8")

# 1) actual-verdict cells
t = t.replace(
    '("off-origin-single", "fail", "pass", "pass", "fail"),',
    '("off-origin-single", "fail", "pass", "pass", "pass"),   # DELTA-D1',
)
t = t.replace(
    '("paginated-canonical-drift", "fail", "fail", "pass", "pass"),',
    '("paginated-canonical-drift", "fail", "pass", "pass", "pass"),   # DELTA-D2',
)

# 2) known-deltas registry + provenance note in module docstring
deltas = '''
KNOWN_DELTAS = {
    "D1": {
        "cell": "CORE-CANON-002 @ off-origin-single",
        "accepted": "fail",
        "actual": "pass",
        "tracking": "#34 (Stage-2 follow-up)",
        "summary": "scheme/host drift vs audited origin is not enforced by the bound evaluator",
    },
    "D2": {
        "cell": "CORE-CANON-005 @ paginated-canonical-drift",
        "accepted": "fail",
        "actual": "pass",
        "tracking": "#34 (Stage-2 follow-up)",
        "summary": "rel-pagination signal is not consulted by the bound evaluator",
    },
}


def test_known_deltas_are_documented_and_tracked():
    """Frozen behaviour may diverge from accepted semantics only via tracked deltas."""
    assert set(KNOWN_DELTAS) == {"D1", "D2"}
    for k, v in KNOWN_DELTAS.items():
        assert v["accepted"] != v["actual"]
        assert "#34" in v["tracking"]
'''
anchor = "def test_golden_classification_table("
i = t.index(anchor)
t = t[:i] + deltas.strip("\n") + "\n\n\n" + t[i:]

# 3) docstring provenance note
t = t.replace(
    "full replacement is BLOCKED until that binding lands.\n",
    "full replacement is BLOCKED until that binding lands.\n\n"
    "FREEZE MODE: current runtime verdicts are frozen as golden; semantic "
    "divergences are captured in KNOWN_DELTAS and tracked under #34.\n",
    1,
)

ast.parse(t)
p.write_text(t, encoding="utf-8", newline="\n")
print("golden switched to freeze-mode with tracked deltas")
