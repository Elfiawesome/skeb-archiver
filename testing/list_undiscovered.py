from pathlib import Path
from typing import Callable, Any
import json

BASE_DIR = Path().resolve()
SKEB_DIR = BASE_DIR / "skeb"

existing: set[str] = set()
candidates: set[str] = set()
for file in SKEB_DIR.glob("*.json"):
	with file.open("r", encoding='utf-8') as f:
		u = json.load(f)
		
		sn = u.get("screen_name")
		if sn:
			existing.add(sn)

		profile = u.get("profile") or {}
		for sc in profile.get("similar_creators") or []:
			csn = sc.get("screen_name")
			if csn:
				candidates.add(csn)

new_names = candidates - existing

with (BASE_DIR/"new_names.txt").open("w") as f:
	for name in new_names:
		f.write(f"{name}\n")