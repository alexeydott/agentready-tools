import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\docs\stage-f-desc-golden.yaml"
)
t = p.read_text(encoding="utf-8")
old = 'descriptions: ["B" * 130, "C" * 20]'
new = (
    "descriptions: ["
    + repr("B" * 130)
    + ", "
    + repr("C" * 20)
    + "]"
)
assert old in t
t = t.replace(old, new, 1)

import yaml  # noqa: E402

doc = yaml.safe_load(t)
print("yaml ok")
p.write_text(t, encoding="utf-8", newline="\n")
