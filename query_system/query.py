from pathlib import Path
from typing import Generator
import json

BASE_DIR = Path().resolve()
SKEB_DIR = (BASE_DIR / "docs" / "skeb")
OUTPUT_FILE = (BASE_DIR / "query-export.csv")

def main() -> None:
	# CONFIGURE HERE
	FILTER_FUNC = filter_content
	SORT_FUNC = sort_content
	MAX_PROCESS = -1

	print(f"Started query!")
	total_items: list[list] = []
	process_count = 0
	for file in get_users(SKEB_DIR):
		with file.open("r", encoding="utf-8") as f:
			data: dict = json.load(f)
			screen_name: str = data.get("screen_name", "")
			first_seen: float = data.get("first_seen", 0.0)
			last_updated: float = data.get("last_updated", 0.0)
			profile: dict = data.get("profile", {})
			price_history: dict = data.get("price_history", {})

			added_item = FILTER_FUNC(screen_name, first_seen, last_updated, profile, price_history)
			if added_item != None: total_items.append(added_item)
		
		process_count += 1
		if process_count >= MAX_PROCESS and MAX_PROCESS > 0: break
	
	print("Sorting items!")
	total_items = SORT_FUNC(total_items)

	print("Writing file!")
	with OUTPUT_FILE.open("w") as f:
		for i in total_items:
			item_count = 0
			for item in i:
				f.write(f"{item}")
				item_count += 1
				if item_count < len(i): f.write(", ")
			f.write("\n")
	print(f"Completed query and exported items to {OUTPUT_FILE}")

# --- CONFIGURABLE FILTERS & SORTS ---

def filter_content(screen_name: str, first_seen: float, last_updated: float, profile: dict, price_history: dict) -> list | None:
	def get_price(art_type: str) -> list[dict]:
		ph: list[dict] = price_history.get(art_type, [])
		if ph:
			ph.sort(key=lambda x: -x["recorded_at"])
			return ph
		return []
	
	def get_latest__price_change(sorted_price_history: list[dict]) -> float:
		if len(sorted_price_history) < 2: return 0
		
		latest_price = sorted_price_history[0]
		second_latest_price: dict = None
		for p in sorted_price_history:
			if p["amount"] != latest_price["amount"]:
				second_latest_price = p
				break
		
		if second_latest_price == None: return 0
		return latest_price["amount"] - second_latest_price["amount"]

	# Price Get
	art_price_change = get_latest__price_change(get_price("art"))
	if art_price_change >= 0: return None
	
	# Normal stuff
	art_current_price = get_price("art")[0].get("amount")
	nsfw_acceptable = profile.get("nsfw_acceptable", False)
	received_works_count =len(profile.get("received_works", []))
	
	return [screen_name, art_current_price, received_works_count, art_price_change, "NSFW" if nsfw_acceptable else "..."]

def sort_content(items: list) -> list:
	return sorted(items, key=lambda x: (
		x[1], # Sort first by low-high price
		-x[2], # Sort by most-least work count
		x[3], # Sort by low-high price change
		x[4] # Sort by nsfw
	))

def get_users(directory: Path) -> Generator[Path, None, None]:
	# return directory.rglob("ramune_skb*.json") # Specifc
	return directory.rglob("*.json") # Default

if __name__ == "__main__":
	main()