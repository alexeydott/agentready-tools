import pathlib

p = pathlib.Path(r"D:\projects\externals\agentready-tools\src\agentready\audit_core\link_evaluators.py")
src = p.read_text(encoding="utf-8")
i = src.find('"CORE-LINK-001"')
print(repr(src[max(0, i - 120) : i + 420]))
