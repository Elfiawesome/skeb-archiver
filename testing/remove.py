from pathlib import Path
import json
BASE_DIR = Path().resolve() / "skeb"


for file in BASE_DIR.glob("*.json"):
	data: dict = {}
	with file.open("r", encoding="utf-8") as f:
		data = json.load(f)
	if "works" in data:
		data.pop("works")
	with file.open("w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False)