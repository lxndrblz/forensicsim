import json
from pathlib import Path

with Path("target.json").open() as json_file:
    data_target = json.load(json_file)

with Path("current.json").open() as json_file:
    data_current = json.load(json_file)

data_target = set(data_target)
data_current = set(data_current)

print(len(data_target))
print(len(data_current))
print("-" * 8)
print(data_target.difference(data_current))
print(data_current.difference(data_target))
