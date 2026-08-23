import ast
import pathlib

p = pathlib.Path(
    r"D:\projects\externals\agentready-tools\docs\stage-f-desc-golden.yaml"
)
t = p.read_text(encoding="utf-8")

t = t.replace("descriptions: ['A' * 140]", "descriptions: [" + repr("A" * 140) + "]")
t = t.replace("descriptions: ['   ']", 'descriptions: ["   "]')
t = t.replace(
    "descriptions: ['B' * 130, 'C' * 20]",
    "descriptions: [" + repr("B" * 130) + ", " + repr("C" * 20) + "]",
)
t = t.replace("descriptions: ['D' * 100]", "descriptions: [" + repr("D" * 100) + "]")
t = t.replace("descriptions: ['E' * 200]", "descriptions: [" + repr("E" * 200) + "]")

import yaml  # noqa: E402

doc = yaml.safe_load(t)
sc = {x["name"]: x for x in doc["scenarios"]}
assert len(sc["in-band-present"]["descriptions"][0]) == 140
p.write_text(t, encoding="utf-8", newline="\n")
print("desc manifest literals fixed")
