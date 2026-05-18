import re
import json
import hashlib
from typing import Generator
from pathlib import Path
from .logger import log
from datetime import datetime, timezone

USERNAME_SAFE_RE = re.compile(r"[^\w\-.]")

class DataStore:
	def __init__(self, base_dir: str) -> None:
		self._root = Path(base_dir)
		self._root.mkdir(parents=True, exist_ok=True)
		self.timestamp = datetime.now(timezone.utc).timestamp()
		log.info("Initialized Data Store.")
	
	def _path(self, file_name: str) -> Path:
		return self._root / f"{DataStore._username_safe(file_name)}.json"

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
		for p in sorted(self._root.glob("*.json")):
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
		with p.open("w", encoding="utf-8") as fh:
			json.dump(data, fh, ensure_ascii=False)
	
	def update_save(self, screen_name: str, profile_data: dict[str]) -> None:
		ori_data = self.load(screen_name)
		new_data: dict[str]
		if ori_data:
			new_data = ori_data
			ori_data["profile"] = profile_data
			ori_data["last_updated"] = self.timestamp
		else:
			new_data = self.new_user(screen_name, self.timestamp)
		
		# Update price
		price_history: dict[str, list[dict]] = new_data.get("price_history", {})
		profile: dict = new_data.get("profile", {})
		skills: list[dict[str]] = profile.get("skills", [])
		for sk in skills:
			genre: str = sk.get("genre", "unknown")
			amt: float = sk.get("default_amount", 0)
			
			if not genre in price_history: price_history[genre] = []
			history_entires = price_history.get(genre)
			
			if history_entires[-1].get("amount") == amt: continue
			
			history_entires.append({"amount": amt, "recorded_at": self.timestamp})

		self.save(new_data)

	@staticmethod
	def new_user(screen_name: str, ts: float) -> dict[str]:
		return {
			"screen_name": screen_name,
			"first_seen": ts,
			"last_updated": ts,
			"profile": {},
			"price_history": {},
		}

	@staticmethod
	def _username_safe(name: str) -> str:
		safe_name = USERNAME_SAFE_RE.sub("_", name)
		h = hashlib.md5(name.encode('utf-8')).hexdigest()[:6]
		return f"{safe_name}-{h}"
