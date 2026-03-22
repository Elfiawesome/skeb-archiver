from pathlib import Path
import json
from datetime import datetime

BASE_DIR = Path().resolve() / "skeb"

for file in BASE_DIR.glob("*.json"):
	first_seen: datetime = 0.0
	last_updated: datetime = 0.0
	d: dict = {}
	with file.open("rb") as f: d = json.load(f)
	if not type(d["first_seen"]) is str: 
		print("first_seen is not a string!")
		continue
	if not type(d["last_updated"]) is str:
		print("last_updated is not a string!")
		continue
	
	first_seen = datetime.fromisoformat(d["first_seen"])
	last_updated = datetime.fromisoformat(d["last_updated"])
	d["first_seen"] = first_seen.timestamp()
	d["last_updated"] = last_updated.timestamp()

	for work_type in d["price_history"]:
		for work_price in d["price_history"][work_type]:
			if not type(work_price["recorded_at"]) is str: 
				print("recorded_at is not a string!")
				continue
			recorded_at = datetime.fromisoformat(work_price["recorded_at"])
			work_price["recorded_at"] = recorded_at.timestamp()

	with file.open("w", encoding="utf-8") as f: json.dump(d, f)


# 3.20 GB
# 3.39 GB