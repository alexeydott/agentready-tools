import ast
import pathlib

EV = pathlib.Path(
    r"D:\projects\externals\agentready-tools-e5-core-link\src\agentready\audit_core\link_evaluators.py"
)
DST = pathlib.Path(r"D:\projects\externals\agentready-tools\src\agentready\audit_core\link_evaluators.py")

src = EV.read_text(encoding="utf-8")
dst = DST.read_text(encoding="utf-8")

# take amended families map + registry scoping from the e5 branch (already reviewed lineage)
import re

for pat in (
    r'    "CORE-LINK-001": \(\("page", "1"\), \("representation", "1"\)\),',
    r'    "CORE-LINK-003": \(\("page", "1"\),\),',
):
    pass

# 1) families: master rows -> amended (001/003/004/006 {page}; 002/005 {page,resources})
old_fams = re.search(
    r'_FACTS_BY_RULE = \{.*?\n\}', dst, re.S
)
assert old_fams, "families map not found"
new_fams = '''_FACTS_BY_RULE = {
    "CORE-LINK-001": (("page", "1"),),
    "CORE-LINK-002": (("page", "1"), ("resources", "1")),
    "CORE-LINK-003": (("page", "1"),),
    "CORE-LINK-004": (("page", "1"),),
    "CORE-LINK-005": (("page", "1"), ("resources", "1")),
    "CORE-LINK-006": (("page", "1"),),
}'''
dst = dst[: old_fams.start()] + new_fams + dst[old_fams.end() :]

pathlib.Path(r"D:\projects\externals\agentready-tools\_marker.txt").write_text(
    "step1 done", encoding="utf-8"
)
print("families map updated")
