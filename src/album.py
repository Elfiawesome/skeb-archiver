import json, gzip, struct
from .logger import log

class AlbumBuilder:
	def __init__(self) -> None:
		self.data = []
		self.time: float = 0.0
		self.name: str = ""
		self.label: str = ""
		self.album_type: str = "full"

	def add_entry(self, raw_user: dict[str]) -> 'AlbumBuilder':
		user = UserDataExt(raw_user)
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

	def add_sparse_entry(self, entry: dict[str]) -> 'AlbumBuilder':
		self.data.append(entry)
		return self
	
	def set_date(self, timestamp: float) -> 'AlbumBuilder':
		self.time = timestamp
		return self
	
	def set_name(self, name: str) -> 'AlbumBuilder':
		self.name = name
		return self

	def set_label(self, label: str) -> 'AlbumBuilder':
		self.label = label
		return self

	def set_type(self, album_type: str) -> 'AlbumBuilder':
		self.album_type = album_type
		return self
	
	def is_empty(self) -> bool:
		return len(self.data) == 0

	#  Metadata builders/unbuilders
	def build_metadata_bytes(self) -> bytes:
		return json.dumps({
			"name": self.name,
			"label": self.label or self.name,
			"type": self.album_type,
			"timestamp": self.time
		}, ensure_ascii=False).encode("utf-8")

	def unbuild_metadata(self, meta: dict[str]) -> 'AlbumBuilder':
		self.name = meta.get("name", "")
		self.label = meta.get("label", "")
		self.album_type = meta.get("type", "full")
		self.time = meta.get("timestamp", 0.0)
		return self

	# Full builders/unbuilders
	def build(self) -> bytes:
		meta_bytes = self.build_metadata_bytes()
		data_json = json.dumps(self.data, ensure_ascii=False).encode("utf-8")
		compressed_data = gzip.compress(data_json)

		result = struct.pack('>I', len(meta_bytes))
		result += meta_bytes
		result += struct.pack('>I', len(compressed_data))
		result += compressed_data
		return result

	@staticmethod
	def unpack_metadata(data: bytes) -> tuple[int, bytes] | None:
		try:
			if len(data) < 8: return None
			meta_size = struct.unpack('>I', data[:4])[0]
			if len(data) < 4 + meta_size: return None
			meta_bytes = data[4:4 + meta_size]
			return meta_size, meta_bytes
		except (struct.error, UnicodeDecodeError, json.JSONDecodeError):
			return None

	@staticmethod
	def unbuild(data: bytes) -> 'AlbumBuilder':
		try:
			meta_size, meta_bytes = AlbumBuilder.unpack_metadata(data)
			meta_dict = json.loads(meta_bytes.decode("utf-8"))

			compressed_start = 4 + meta_size
			compressed_size = struct.unpack('>I', data[compressed_start:compressed_start + 4])[0]
			if len(data) < compressed_start + 4 + compressed_size:
				return None
			compressed_data = data[compressed_start + 4 : compressed_start + 4 + compressed_size]

			json_data = gzip.decompress(compressed_data)
			entries = json.loads(json_data.decode("utf-8"))
			
			if not isinstance(entries, list): return None

			ab = AlbumBuilder()
			ab.unbuild_metadata(meta_dict)
			ab.data = entries
			return ab

		except (struct.error, UnicodeDecodeError, json.JSONDecodeError, gzip.BadGzipFile, OSError) as e:
			return None


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
		avatar_url = self.profile.get("avatar_url", "")
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
	def first_seen(self) -> float:
		fs = self.data.get("first_seen", 0)
		return fs if isinstance(fs, float) else 0

	@property
	def last_updated(self) -> float:
		lu = float(self.data.get("last_updated", 0))
		return lu 
	
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
