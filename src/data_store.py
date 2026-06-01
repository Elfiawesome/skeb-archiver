import re
import json
import hashlib
from typing import Generator
from pathlib import Path
from .logger import log
from .album import AlbumBuilder
from datetime import datetime, timezone

USERNAME_SAFE_RE = re.compile(r"[^\w\-.]")

class DataStore:
	def __init__(self, docs_dir: str, persistance_dir: str = None) -> None:
		self._docs_dir = Path(docs_dir)
		
		self._skeb_dir = self._docs_dir / "skeb"
		self._skeb_dir.mkdir(parents=True, exist_ok=True)

		self._albums_dir = self._docs_dir / "albums"
		self._albums_dir.mkdir(parents=True, exist_ok=True)

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
		if not user_data: return # If user doesn't exist
		
		if "custom" not in user_data: user_data["custom"] = {}
		return user_data["custom"]
	
	def update_custom_data(self, screen_name: str, key: str, data: object | None) -> None:
		user_data: dict[str] = self.load(screen_name)
		if not user_data: return # If user doesn't exist
		
		if data is None:
			user_data["custom"].pop(key)
		else:
			user_data["custom"][key] = data
		
		ts = self.timestamp_now()
		user_data["last_updated"] = ts
		
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
	
	def create_api_data(self, max_chunk_mb: int = 1) -> None:
		log.info("Started creating static api data.")

		album = AlbumBuilder() \
			.set_name("main_index") \
			.set_label("All Artists") \
			.set_type("full") \
			.set_date(datetime.now(tz=timezone.utc).timestamp())

		for u in self.load_all():
			album.add_entry(u)

		self.store_album(album, self._albums_dir, max_chunk_mb)
		self._build_album_index()

	def _build_album_index(self) -> None:
		import struct
		index: dict[str, dict] = {}
		for album_dir in sorted(self._docs_dir.glob("**/*.album")):
			name = album_dir.name.replace(".album", "")
			chunk1 = album_dir / f"{name}.1"
			if not chunk1.exists():
				continue
			parent_rel = str(album_dir.parent.relative_to(self._docs_dir)).replace("\\", "/")
			rel_path = f"{parent_rel}/{name}" if parent_rel != "." else name
			try:
				with open(chunk1, "rb") as f:
					header = f.read(1024 * 64)
				meta = AlbumBuilder.parse_metadata_from_bytes(header)
				index[rel_path] = {
					"label": meta.get("label", name),
					"type": meta.get("type", "curated")
				}
			except (json.JSONDecodeError, UnicodeDecodeError, struct.error) as e:
				log.warning("Skipping album %s (old format?): %s", name, e)
				index[rel_path] = {"label": name, "type": "unknown"}

		index_path = self._albums_dir / "index.json"
		with index_path.open("w", encoding="utf-8") as f:
			json.dump(index, f, ensure_ascii=False, indent=2)
		log.info("Album index written to %s (%d albums)", index_path, len(index))

	def store_album(self, album: AlbumBuilder, path: Path, max_chunk_mb: int = 1) -> None:
		album_dir = path / f"{album.name}.album"
		album_dir.mkdir(parents=True, exist_ok=True)

		data_bytes = album.build()

		chunk_size = max_chunk_mb * 1024 * 1024
		num_chunks = (len(data_bytes) + chunk_size - 1) // chunk_size

		for i in range(num_chunks):
			start = i * chunk_size
			end = min(start + chunk_size, len(data_bytes))
			chunk = data_bytes[start:end]

			chunk_path = album_dir / f"{album.name}.{i+1}"
			with open(chunk_path, "wb") as f:
				f.write(chunk)