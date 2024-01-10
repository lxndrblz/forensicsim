import json
from copy import deepcopy
from pathlib import Path

with Path("target.json").open() as json_file:
    data_target = json.load(json_file)

with Path("current.json").open() as json_file:
    data_current = json.load(json_file)

print("length")
print(len(data_target))
print(len(data_current))

# manually remove attributes missing in legacy implementation
for el in data_target:
    el["origin_file"] = None
    el["attachments"] = None
    el["clientArrivalTime"] = None
for el in data_current:
    el["clientArrivalTime"] = None
    el["origin_file"] = None
    el["attachments"] = None

# some files have windows paths others linux paths
data_current_copy = deepcopy(data_current)
data_target_copy = deepcopy(data_target)

for el in data_current_copy:
    if el in data_target:
        data_target.remove(el)
for el in data_target_copy:
    if el in data_current:
        data_current.remove(el)

print("\n" * 5)

print("remainder of data_current")
print(data_current)

print("\n" * 5)
print("remainder of data_target")
print(data_target)

print("length")
print(len(data_target))
print(len(data_current))
