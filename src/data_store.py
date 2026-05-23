import re
import json
import hashlib
from typing import Generator
from pathlib import Path
from .logger import log
from datetime import datetime, timezone

USERNAME_SAFE_RE = re.compile(r"[^\w\-.]")

class DataStore:
	def __init__(self, docs_dir: str, persistance_dir: str = None) -> None:
		self._docs_dir = Path(docs_dir)
		
		self._skeb_dir = self._docs_dir / "skeb"
		self._skeb_dir.mkdir(parents=True, exist_ok=True)

		self._api_dir = self._docs_dir / "api"
		self._api_dir.mkdir(parents=True, exist_ok=True)

		self._persistance_dir = Path(persistance_dir) if persistance_dir else Path(self._skeb_dir.parent)
		self._persistance_dir.mkdir(parents=True, exist_ok=True)
		
		self.start_time = self.timestamp_now()
		log.info("Initialized Data Store.")
	
	def timestamp_now(self) -> float:
		return datetime.now(timezone.utc).timestamp()

	def _path(self, file_name: str) -> Path:
		return self._skeb_dir / f"{DataStore._username_safe(file_name)}.json"

	def load(self, screen_name: str) -> dict[str] | None:
		p = self._path(screen_name)
		if not p.exists(): return None
		
		try:
			with p.open("r", encoding="utf-8") as fh:
				return json.load(fh)
		except (json.JSONDecodeError, OSError) as e:
			log.warning("Corrupt file %s: %s", p, e)
			return None
		
	def load_all(self) -> Generator[dict[str], None, None]:
		for p in sorted(self._skeb_dir.glob("*.json")):
			try:
				with p.open("r", encoding="utf-8") as fh:
					yield json.load(fh)
			except (json.JSONDecodeError, OSError) as e:
				log.warning("Skipping corrupt file %s: %s", p, e)

	def save(self, data: dict[str]) -> None:
		name = data.get("screen_name")
		if not name:
			log.warning("Cannot save record without screen_name.")
			return
		p = self._path(name)
		log.info(f"Saving at {p}")
		with p.open("w", encoding="utf-8") as fh:
			json.dump(data, fh, ensure_ascii=False)
	
	def get_custom_data(self, screen_name: str, key: str):
		user_data = self.load(screen_name)
		if "custom" not in user_data: user_data["custom"] = {}
		return user_data["custom"]
	
	def update_custom_data(self, screen_name: str, key: str, data: object | None) -> None:
		user_data: dict[str] = self.load(screen_name)
		
		if data is None:
			user_data["custom"].pop(key)
		else:
			user_data["custom"][key] = data
		self.save(user_data)

	def update_save(self, screen_name: str, new_profile_data: dict[str]) -> dict[str]:
		ts = self.timestamp_now()
		old_data = self.load(screen_name)
		new_data: dict[str] = None
		if old_data:
			# Update what is needed
			old_data["profile"] = new_profile_data
			old_data["last_updated"] = ts
			new_data = old_data
		else:
			# Create new save
			new_data = self.new_user(screen_name, ts)
			new_data["profile"] = new_profile_data
		
		self._update_price(new_data, ts)

		self.save(new_data)
		return new_data

	def _update_price(self, user_data: dict[str], ts: float) -> None:
		if "price_history" not in user_data:
			user_data["price_history"] = {}
		price_history: dict[str, list[dict[str]]] = user_data["price_history"]

		profile: dict = user_data.get("profile", {})
		skills: list[dict[str]] = profile.get("skills", [])
		for sk in skills:
			genre: str = sk.get("genre", "unknown")
			amt: float | None = sk.get("default_amount", None)

			if not genre in price_history: price_history[genre] = []
			history_entires = price_history.get(genre)
			
			if history_entires and history_entires[-1].get("amount") == amt:
				continue
			
			history_entires.append({"amount": amt, "recorded_at": ts})

	@staticmethod
	def new_user(screen_name: str, ts: float) -> dict[str]:
		return {
			"screen_name": screen_name,
			"first_seen": ts,
			"last_updated": ts,
			"profile": {},
			"price_history": {},
			"custom": {} # Transfer flags here
		}

	@staticmethod
	def _username_safe(name: str) -> str:
		safe_name = USERNAME_SAFE_RE.sub("_", name)
		h = hashlib.md5(name.encode('utf-8')).hexdigest()[:6]
		return f"{safe_name}-{h}"

	def open_session_date_folder(self) -> Path:
		new_path: Path = self._persistance_dir / datetime.fromtimestamp(self.start_time, tz=timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
		new_path.mkdir(parents=True, exist_ok=True)
		return new_path
	
	def create_api_data(self) -> None:
		def _true_works_count(profile: dict) -> int:
			c = profile.get("received_works_count")
			if isinstance(c, int): return c
			rw = profile.get("received_works")
			return len(rw) if isinstance(rw, list) else 0

		def _get_received_works(profile: dict) -> list[dict[str]]:
			rw = profile.get("received_works")
			return rw if isinstance(rw, list) else []
		
		def _current_prices(ph: dict[str, list]) -> dict[str]:
			return {g: e[-1].get("amount") for g, e in ph.items() if e}

		def _price_ranges(ph: dict[str, list]) -> dict[str, dict[str]]:
			out: dict[str, dict[str]] = {}
			for genre, entries in ph.items():
				amounts = [e["amount"] for e in entries if e.get("amount") is not None]
				if amounts:
					out[genre] = {"min": min(amounts), "max": max(amounts)}
			return out
	
		def _latest_thumbnail_urls(works: list[dict], max_count: int = 4) -> list[str]:
			urls: list[str] = []
			for w in works:
				thumb = _extract_thumbnail(w)
				if thumb["src"]:
					urls.append(_pick_best_url(thumb["srcset"], thumb["src"]))
					if len(urls) >= max_count:
						break
			return urls
		
		def _extract_thumbnail(work: dict) -> dict[str, str]:
			for key in ("thumbnail_image_urls", "private_thumbnail_image_urls"):
				urls = work.get(key)
				if isinstance(urls, dict) and urls.get("src"):
					return {"src": urls["src"], "srcset": urls.get("srcset", "")}
			return {"src": "", "srcset": ""}


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

		log.info("Started creating static api pages.")

		pages_dir = self._api_dir / "pages"
		pages_dir.mkdir(parents=True, exist_ok=True)
	
		index_entries: list[dict[str]] = []

		for u in self.load_all():
			sn = u.get("screen_name", "")
			if not sn: continue
			
			ph = u.get("price_history", {})
			profile: dict = u.get("profile", {})
			avatar = profile.get("avatar_url", "")
			file_key = DataStore._username_safe(sn)
			works = _get_received_works(profile)
			total_works = _true_works_count(profile)
			custom_data = u.get("custom", {})
			acceptable = bool(profile.get("acceptable", False))
			nsfw_acceptable = bool(profile.get("nsfw_acceptable", False))
			
			index_entries.append({
				"screen_name": sn,
				"file": file_key,
				"avatar_url": avatar,
				"total_works": total_works,
				"first_seen": u.get("first_seen", ""),
				"last_updated": u.get("last_updated", ""),
				"current_prices": _current_prices(ph),
				"price_range": _price_ranges(ph),
				"latest_thumbnails": _latest_thumbnail_urls(works, 4),
				"custom": custom_data,
				"acceptable": acceptable,
				"nsfw": nsfw_acceptable,
			})

		import math, gzip
		PAGE_SIZE = 20000
		page_size = PAGE_SIZE
		total_pages = max(1, math.ceil(len(index_entries) / page_size))
		for page_num in range(total_pages):
			start = page_num * page_size
			page_data = {"page": page_num, "users": index_entries[start:start + page_size]}
			with (pages_dir / f"{page_num}.json.gz").open("wb") as f_out, gzip.open(f_out, "wt", encoding="utf-8") as fh:
				json.dump(page_data, fh, ensure_ascii=False)

		index = {
			"generated_at": datetime.now(timezone.utc).timestamp(),
			"user_count": len(index_entries),
			"page_size": page_size,
			"total_pages": total_pages,
			# "known_flags": sorted(all_flag_names),
		}
		with (self._api_dir / "index.json").open("w", encoding="utf-8") as fh:
			json.dump(index, fh, ensure_ascii=False)
		
		log.info(f"Finished api pages wih {index['user_count']} users.")