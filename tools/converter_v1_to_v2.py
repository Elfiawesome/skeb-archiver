from pathlib import Path
import gzip
import json

BASE_DIR = Path().resolve()
SKEB_DIR = (BASE_DIR / "docs" / "skeb")

users = {}
for i in SKEB_DIR.rglob("*.json"):
	print(i)
	data: dict = {}
	with i.open("r", encoding="utf-8") as f:
		data = json.load(f)
	
	old_custom = data.copy()
	for k in ["screen_name", "first_seen", "last_updated", "profile", "price_history"]:
		old_custom.pop(k)
	
	if "custom" not in data: data["custom"] = {}
	new_custom: dict = data["custom"]
	merged_custom = new_custom | old_custom
	data["custom"] = merged_custom

	with i.open("w", encoding="utf-8") as f:
		json.dump(data, f)