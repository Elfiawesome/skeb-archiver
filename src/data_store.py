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