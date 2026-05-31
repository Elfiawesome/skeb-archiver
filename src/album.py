import json, gzip, struct

class AlbumBuilder:
	def __init__(self) -> None:
		self.data = []
		self.time: float = 0.0
		self.name: str = ""

	def add_entry(self, raw_user: dict[str]) -> 'AlbumBuilder':
		user = UserDataExt(raw_user) # Wraper
		screen_name = user.screen_name
		if screen_name == "": return self
		
		avatar = user.avatar_url
		file_key = user.file_key
		total_works = user.true_work_count
		custom_data = user.custom_data
		acceptable = user.acceptable
		nsfw_acceptable = user.nsfw_acceptable

		i: dict[str] = {}
		i["screen_name"] = screen_name
		if file_key: i["file"] = file_key
		if avatar: i["avatar_url"] = avatar
		if total_works: i["total_works"] = total_works
		if user.first_seen: i["first_seen"] = user.first_seen
		if user.last_updated: i["last_updated"] = user.last_updated
		if user.current_prices: i["current_prices"] = user.current_prices
		if user.price_ranges: i["price_range"] = user.price_ranges
		_url_thumbnails = user.latest_thumbnail_urls(4)
		if _url_thumbnails: i["latest_thumbnails"] = _url_thumbnails
		if custom_data: i["custom"] = custom_data
		if acceptable: i["acceptable"] = acceptable
		if nsfw_acceptable: i["nsfw"] = nsfw_acceptable

		self.data.append(i)
		return self
	
	def set_date(self, timestamp: float) -> 'AlbumBuilder':
		self.time = timestamp
		return self
	
	def set_name(self, name: str) -> 'AlbumBuilder':
		self.name = name
		return self

	def build(self) -> bytes:
		bytes_data = json.dumps({
			"name": self.name,
			"timestamp": self.time,
			"data":self.data
		}, ensure_ascii=False).encode("utf-8")
		compressed_bytes_data = gzip.compress(bytes_data)
		size_bytes = struct.pack('>I', len(compressed_bytes_data))
		return size_bytes + compressed_bytes_data
	
	def is_empty(self) -> bool:
		return len(self.data) == 0



class UserDataExt:
	def __init__(self, data: dict[str]):
		self.data = data

	@property
	def screen_name(self) -> str:
		sn = self.data.get("screen_name", "")
		return sn if isinstance(sn, str) else ""
	
	@property
	def price_history(self) -> dict[str, list[dict[str]]]:
		ph = self.data.get("price_history", {})
		return ph if isinstance(ph, dict) else {}
	
	@property
	def profile(self) -> dict[str]:
		profile = self.data.get("profile", {})
		return profile if isinstance(profile, dict) else {}
	
	@property
	def avatar_url(self) -> str:
		avatar_url = self.data.get("avatar_url", "")
		return avatar_url if isinstance(avatar_url, str) else ""

	@property
	def file_key(self) -> str | None:
		from .data_store import DataStore
		return DataStore._username_safe(self.screen_name) # No need to check since it's always a string
	
	@property
	def works(self) -> list[dict[str]]:
		rw = self.profile.get("received_works")
		return rw if isinstance(rw, list) else []

	@property
	def true_work_count(self) -> int:
		c = self.profile.get("received_works_count")
		if isinstance(c, int): return c
		rw = self.profile.get("received_works")
		return len(rw) if isinstance(rw, list) else 0

	@property
	def custom_data(self) -> dict[str]:
		cd = self.data.get("custom", {})
		return cd if isinstance(cd, dict) else {}
	
	@property
	def acceptable(self) -> bool:
		a = self.profile.get("acceptable", False)
		return bool(a)
	
	@property
	def nsfw_acceptable(self) -> bool:
		na = self.profile.get("nsfw_acceptable", False)
		return bool(na)
	
	@property
	def first_seen(self) -> int:
		fs = self.data.get("first_seen", 0)
		return fs if isinstance(fs, int) else 0

	@property
	def last_updated(self) -> int:
		lu = self.data.get("last_updated", 0)
		return lu if isinstance(lu, int) else 0
	
	@property
	def current_prices(self) -> dict[str]:
		ph = self.price_history
		return {g: e[-1].get("amount") for g, e in ph.items() if e}

	@property
	def price_ranges(self):
		out: dict[str, dict[str]] = {}
		for genre, entries in self.price_history.items():
			amounts = [e["amount"] for e in entries if e.get("amount") is not None]
			if amounts:
				out[genre] = {"min": min(amounts), "max": max(amounts)}
		return out
	
	
	def latest_thumbnail_urls(self, max_count: int = 4) -> list[str]:
		urls: list[str] = []
		for w in self.works:
			thumb = self._extract_thumbnail(w)
			if thumb["src"]:
				urls.append(self._pick_best_url(thumb["srcset"], thumb["src"]))
				if len(urls) >= max_count:
					break
		return urls

	@staticmethod
	def _extract_thumbnail(work: dict[str]) -> dict[str, str]:
		for key in ("thumbnail_image_urls", "private_thumbnail_image_urls"):
			urls = work.get(key)
			if isinstance(urls, dict) and urls.get("src"):
				return {"src": urls["src"], "srcset": urls.get("srcset", "")}
		return {"src": "", "srcset": ""}

	@staticmethod
	def _pick_best_url(srcset: str, fallback: str = "") -> str:
		if not srcset:
			return fallback
		parts = [p.strip() for p in srcset.split(",") if p.strip()]
		for target in ("3x", "2x"):
			for part in parts:
				tokens = part.rsplit(None, 1)
				if len(tokens) == 2 and tokens[1] == target:
					return tokens[0]
		if parts:
			return parts[0].split()[0]
		return fallback
