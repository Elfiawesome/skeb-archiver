# Purpose: Get all users who have 0 posts, then we get their twitter and export them
from pathlib import Path
import json

BASE_DIR = Path().resolve()
SKEB_DIR = BASE_DIR / "skeb"

total_list: list[tuple[int, str, str]] = []

i = 0
for file in SKEB_DIR.glob("*.json"):
	with file.open("r", encoding='utf-8') as f:
		i+=1
		print(f"{i} / 105092 [{float(i)/105092*100:.2}%]" )
		u: dict = json.load(f)
		p: dict = u.get("profile", {})

		if len(p.get("received_works", [])) < 1:
			screen_name = u.get("screen_name", None)
			twt_link = None
			
			price = u["price_history"].get("art", [])
			if price:
				price_amt = int(price[0]["amount"])
			if not price_amt:
				continue
			
			for userlinks in p.get("user_service_links", []):
				if userlinks["provider"] == "twitter":
					twt_link = userlinks["url"] + "/media"
		
			if screen_name and twt_link:
				total_list.append((price_amt, f"https://skeb.jp/@{screen_name}", twt_link))

total_list.sort(key=lambda x: x[0])


with (BASE_DIR/"twitter-usersname-with-empty-profiles.txt").open("w") as f:
	for price, skeb_link, twt_link in total_list:
		f.write(f"{price}, {twt_link}, {skeb_link}\n")