"""
Static-site data generator.

Reads raw user files from ``skeb/`` and writes:
	docs/api/index.json           lightweight table data
	docs/api/users/<name>.json    full detail per user (lazy-loaded)
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logger import log
from .store import DataStore

_SAFE_RE = re.compile(r"[^\w\-.]")

_IMAGE_KEYS = (
	"og_image_url",
	"preview_url",
	"thumbnail_url",
	"preview",
)


def _safe(name: str) -> str:
	return _SAFE_RE.sub("_", name)


def _pick_preview(work: Dict) -> Optional[str]:
	for k in _IMAGE_KEYS:
		v = work.get(k)
		if v:
			return v
	return None


def _current_prices(ph: Dict[str, list]) -> Dict[str, Any]:
	return {
		genre: entries[-1].get("amount")
		for genre, entries in ph.items()
		if entries
	}


def _price_ranges(ph: Dict[str, list]) -> Dict[str, Dict[str, Any]]:
	out: Dict[str, Dict[str, Any]] = {}
	for genre, entries in ph.items():
		amounts = [e["amount"] for e in entries if e.get("amount") is not None]
		if amounts:
			out[genre] = {"min": min(amounts), "max": max(amounts)}
	return out


def generate_data(
	data_dir: str = "skeb",
	output_dir: str = "docs",
) -> None:
	"""
	Read every ``<data_dir>/*.json`` user file and write two kinds of
	output under ``<output_dir>/api/``:

	* ``index.json`` – one small record per user (for the main table)
	* ``users/<name>.json`` – full detail (loaded on demand by the UI)

	Parameters
	----------
	data_dir : str
		Directory that the *crawler* writes to (default ``skeb``).
	output_dir : str
		Root of the static site (default ``docs``).
	"""
	store = DataStore(data_dir)
	all_users = store.load_all()

	api_dir = Path(output_dir) / "api"
	users_dir = api_dir / "users"
	users_dir.mkdir(parents=True, exist_ok=True)

	index_entries: List[Dict[str, Any]] = []

	for u in all_users:
		sn = u.get("screen_name", "")
		if not sn:
			continue

		ph = u.get("price_history", {})
		profile = u.get("profile", {})
		avatar = profile.get("avatar_url", "")
		file_key = _safe(sn)

		# ── lightweight index entry ──────────────────────
		index_entries.append(
			{
				"screen_name": sn,
				"file": file_key,
				"avatar_url": avatar,
				"works_count": len(u.get("works", [])),
				"first_seen": u.get("first_seen", ""),
				"last_updated": u.get("last_updated", ""),
				"current_prices": _current_prices(ph),
				"price_range": _price_ranges(ph),
			}
		)

		# ── full detail file ─────────────────────────────
		works_out: List[Dict[str, Any]] = []
		for w in u.get("works", []):
			works_out.append(
				{
					"path": w.get("path", ""),
					"scraped_at": w.get("scraped_at", ""),
					"preview": _pick_preview(w),
					"genre": w.get("genre", ""),
					"nsfw": w.get("nsfw", False),
					"created_at": w.get("created_at", ""),
					"completed_at": w.get("completed_at", ""),
				}
			)

		detail = {
			"screen_name": sn,
			"file": file_key,
			"name": profile.get("name", ""),
			"avatar_url": avatar,
			"first_seen": u.get("first_seen", ""),
			"last_updated": u.get("last_updated", ""),
			"price_history": ph,
			"current_prices": _current_prices(ph),
			"price_range": _price_ranges(ph),
			"works": works_out,
		}

		with (users_dir / f"{file_key}.json").open("w", encoding="utf-8") as fh:
			json.dump(detail, fh, ensure_ascii=False)

	# ── write index ──────────────────────────────────────
	index = {
		"generated_at": datetime.now(timezone.utc).isoformat(),
		"user_count": len(index_entries),
		"users": index_entries,
	}
	with (api_dir / "index.json").open("w", encoding="utf-8") as fh:
		json.dump(index, fh, ensure_ascii=False)

	log.info(
		"Site data written to %s  (%d users)", api_dir, len(index_entries)
	)