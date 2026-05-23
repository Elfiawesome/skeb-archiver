from pathlib import Path
import json

BASE_DIR = Path().resolve()
SKEB_DIR = (BASE_DIR / "skeb")
OUTPUT_FILE = (BASE_DIR / "listed_users.txt")


current_users: list[str] = []
related_users: list[str] = []

# Getting existing users
for i in SKEB_DIR.rglob("*.json"):
	with i.open("r", encoding="utf-8") as f:
		text = f.read()
		data = json.loads(text)
		
		if "screen_name" in data:
			current_users.append(data["screen_name"])
			
			for sc in data["profile"]["similar_creators"]:
				screen_name = sc["screen_name"]
				if not screen_name in related_users:
					related_users.append(screen_name)

				


print("writing file...")
with OUTPUT_FILE.open("w") as f:
	for screen_name in related_users:
		if screen_name in current_users:
			pass
		else:
			f.write(f"{screen_name}\n")
print(f"done writing to {OUTPUT_FILE}")
