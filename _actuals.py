import sys

sys.path.insert(0, r"D:\projects\externals\agentready-tools\src")
sys.path.insert(0, r"D:\projects\externals\agentready-tools\tests")

import test_stage_f_canon_golden as g  # noqa: E402

for sc in ("duplicated", "missing"):
    print(sc, "->", g._frozen_verdicts(sc))
