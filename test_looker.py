import sys
import os
sys.path.append(os.getcwd())
import json
from scripts.looker_reader import fetch_looker_data

data = fetch_looker_data()
with open("temp_looker_res.json", "w") as f:
    json.dump(data, f, indent=2)
print("Done writing to temp_looker_res.json")
