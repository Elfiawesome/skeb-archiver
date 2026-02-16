from pathlib import Path
import json
import datetime
BASE_DIR = Path().resolve() / "skeb"

for file in BASE_DIR.glob("*.json"):
	data: dict = {}
	with file.open("r", encoding="utf-8") as f:
		data = json.load(f)
	
	last_updated_str = data["last_updated"]
	first_seen_str = data["first_seen"]

	last_updated = datetime.datetime.fromisoformat(last_updated_str)
	first_seen = datetime.datetime.fromisoformat(first_seen_str)

	need_update = False

	if last_updated.utcoffset() == None:
		last_updated = last_updated.astimezone(tz=datetime.timezone.utc)
		data["last_updated"] = last_updated.isoformat()
		need_update = True
	if first_seen.utcoffset() == None:
		first_seen = first_seen.astimezone(tz=datetime.timezone.utc)
		data["first_seen"] = first_seen.isoformat()
		need_update = True
	
	if need_update:
		with file.open("w", encoding="utf-8") as f:
			json.dump(data, f, ensure_ascii=False)
