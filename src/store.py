"""Per-user JSON file store with price-history tracking."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from .logger import log

# Keys managed by the system — everything else is a user-defined flag
SYSTEM_KEYS = frozenset({
	"screen_name", "first_seen", "last_updated", "profile", "price_history",
})


class DataStore:
	"""One JSON file per user under *base_dir*."""

	_SAFE = re.compile(r"[^\w\-.]")

	def __init__(self, base_dir: str = "skeb") -> None:
		self._root = Path(base_dir)
		self._root.mkdir(parents=True, exist_ok=True)
		log.info("Data directory: %s", self._root.resolve())

	def _path(self, screen_name: str) -> Path:
		return self._root / f"{self._SAFE.sub('_', screen_name)}.json"

	def load(self, screen_name: str) -> Optional[Dict[str, Any]]:
		p = self._path(screen_name)
		if not p.exists():
			return None
		try:
			with p.open("r", encoding="utf-8") as fh:
				return json.load(fh)
		except (json.JSONDecodeError, OSError) as e:
			log.warning("Corrupt file %s: %s", p, e)
			return None

	def save(self, data: Dict[str, Any]) -> None:
		name = data.get("screen_name")
		if not name:
			log.warning("Cannot save record without screen_name")
			return
		p = self._path(name)
		with p.open("w", encoding="utf-8") as fh:
			json.dump(data, fh, ensure_ascii=False)

	def load_all(self) -> List[Dict[str, Any]]:
		users: List[Dict[str, Any]] = []
		for p in sorted(self._root.glob("*.json")):
			try:
				with p.open("r", encoding="utf-8") as fh:
					users.append(json.load(fh))
			except (json.JSONDecodeError, OSError) as e:
				log.warning("Skipping corrupt file %s: %s", p, e)
		return users

	def list_screen_names(self, filter_func: Optional[Callable[[dict], bool]] = None) -> List[str]:
		"""Return all screen_names from stored user files."""
		names: List[str] = []
		for p in sorted(self._root.glob("*.json")):
			try:
				with p.open("r", encoding="utf-8") as fh:
					data = json.load(fh)
					sn = data.get("screen_name")
					if filter_func is None or filter_func(data):
						if sn:
							names.append(sn)
			except (json.JSONDecodeError, OSError) as e:
				log.warning("Skipping corrupt file %s: %s", p, e)
		return names

	@staticmethod
	def new_user(screen_name: str, ts: str) -> Dict[str, Any]:
		return {
			"screen_name": screen_name,
			"first_seen": ts,
			"last_updated": ts,
			"profile": {},
			"price_history": {},
		}

	def merge_profile(self, user: Dict, profile: Dict, ts: str) -> None:
		"""Update profile and prices.  All custom keys are preserved."""
		user["profile"] = profile
		user["last_updated"] = ts
		self._update_prices(user, profile, ts)

	@staticmethod
	def _update_prices(user: Dict, profile: Dict, ts: str) -> None:
		history: Dict[str, list] = user.setdefault("price_history", {})
		skills = profile.get("skills")
		if not isinstance(skills, list):
			return
		for sk in skills:
			genre: str = sk.get("genre", "unknown")
			amount = sk.get("default_amount")
			entries = history.setdefault(genre, [])
			if entries and entries[-1].get("amount") == amount:
				continue
			entries.append({"amount": amount, "recorded_at": ts})
			log.debug("Price change: %s / %s -> %s",
					user["screen_name"], genre, amount)