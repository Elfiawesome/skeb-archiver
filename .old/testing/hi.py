from pathlib import Path
import gzip
import json

BASE_DIR = Path().resolve()
SKEB_DIR = (BASE_DIR / "docs" / "skeb")
OUTPUT_FILE = (BASE_DIR / "output.json.gz")

# users = {}
# for i in SKEB_DIR.rglob("*.json"):
# 	with i.open("r", encoding="utf-8") as f:
# 		data = json.load(f)
# 		users[data.get("screen_name")] = data

# with gzip.open(str(OUTPUT_FILE), "wt", encoding="utf-8") as f:
#     json.dump(users, f)


import time
start = time.perf_counter()

with gzip.open(str(OUTPUT_FILE), "rt", encoding="utf-8") as f:
	print("Loading")
	data = json.load(f)
	print("loaded now calc")
	print(len(data))

	data["hiaoshfoahsoufhoasfhoasuhfoaushf"] = {}

end = time.perf_counter()
print(f"Elapsed time: {end - start:.4f} seconds")


start = time.perf_counter()

with gzip.open(str(BASE_DIR / "fuck2.json.gz"), "wt", encoding="utf-8") as f:
	json.dump(data, f)

end = time.perf_counter()
print(f"Elapsed time: {end - start:.4f} seconds")
