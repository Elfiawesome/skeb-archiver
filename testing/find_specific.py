from pathlib import Path
import json

BASE_DIR = Path().resolve()
SKEB_DIR = (BASE_DIR / "skeb")
OUTPUT_FILE = (BASE_DIR / "find_specific_output.csv")

KEYWORDS = [
	"ケモノ",
	"けもの",
	"ケモカス",
	"fursona",
	"furry"
]

items: list[tuple[str, int]] = []

print("scanning and reading files...")
for i in SKEB_DIR.rglob("*.json"):
	with i.open("r", encoding="utf-8") as f:
		text = f.read()
		data = json.loads(text)
		
		price_amt: int | None = None
		price = data["price_history"].get("art", [])
		if price:
			price_amt = int(price[0]["amount"])

		
		for work in data["profile"]["received_works"]:
			text = work.get("body", {})
			if text:
				if any(term in text for term in KEYWORDS):
					link = "https://skeb.jp" + work["path"]
					items.append([link, price_amt])

items.sort(key=lambda x: x[1])

print("writing file...")
with OUTPUT_FILE.open("w") as f:
	for i in items:
		f.write(f"{i[0]}, {i[1]}\n")
print(f"done writing to {OUTPUT_FILE}")
