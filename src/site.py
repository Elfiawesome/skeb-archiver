"""
Static-site data generator.

Reads raw user files from ``data_dir`` and writes:
	<output_dir>/api/index.json             lightweight table data
	<output_dir>/api/users/<file>.json      full detail per user (lazy-loaded)
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logger import log
from .store import DataStore

_SAFE_RE = re.compile(r"[^\w\-.]")


def _safe(name: str) -> str:
	return _SAFE_RE.sub("_", name)


# ── thumbnail helpers ────────────────────────────────────────

def _extract_thumbnail(work: Dict) -> Dict[str, str]:
	"""
	Pull ``src`` and ``srcset`` from ``thumbnail_image_urls``.
	Falls back to ``private_thumbnail_image_urls``.
	"""
	for key in ("thumbnail_image_urls", "private_thumbnail_image_urls"):
		urls = work.get(key)
		if isinstance(urls, dict) and urls.get("src"):
			return {
				"src": urls.get("src", ""),
				"srcset": urls.get("srcset", ""),
			}
	return {"src": "", "srcset": ""}


def _pick_best_url(srcset: str, fallback: str = "") -> str:
	"""
	Return the highest-resolution single URL from a srcset string.

	Prefers 3x > 2x > 1x.
	"""
	if not srcset:
		return fallback
	parts = [p.strip() for p in srcset.split(",") if p.strip()]
	# look for 3x first, then 2x
	for target in ("3x", "2x"):
		for part in parts:
			tokens = part.rsplit(None, 1)
			if len(tokens) == 2 and tokens[1] == target:
				return tokens[0]
	# fallback to the first entry (1x)
	if parts:
		return parts[0].split()[0]
	return fallback


def _latest_thumbnail_url(works: List[Dict]) -> str:
	"""
	Walk works from newest to oldest and return the best single URL
	for the most recent work that has a thumbnail.
	"""
	for w in reversed(works):
		thumb = _extract_thumbnail(w)
		if thumb["src"]:
			return _pick_best_url(thumb["srcset"], thumb["src"])
	return ""


# ── price helpers ────────────────────────────────────────────

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


# ── main entry point ─────────────────────────────────────────

def generate_data(
	data_dir: str = "skeb",
	output_dir: str = "docs",
) -> None:
	"""
	Read every ``<data_dir>/*.json`` user file and produce:

	* ``<output_dir>/api/index.json`` – one small record per user
	* ``<output_dir>/api/users/<file>.json`` – full detail per user
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
		works = u.get("works", [])

		# ── lightweight index entry ──────────────────────
		index_entries.append(
			{
				"screen_name": sn,
				"file": file_key,
				"avatar_url": avatar,
				"works_count": len(works),
				"first_seen": u.get("first_seen", ""),
				"last_updated": u.get("last_updated", ""),
				"current_prices": _current_prices(ph),
				"price_range": _price_ranges(ph),
				"latest_thumbnail_url": _latest_thumbnail_url(works),
			}
		)

		# ── full detail file ─────────────────────────────
		works_out: List[Dict[str, Any]] = []
		for w in works:
			thumb = _extract_thumbnail(w)
			works_out.append(
				{
					"path": w.get("path", ""),
					"scraped_at": w.get("scraped_at", ""),
					"thumbnail_src": thumb["src"],
					"thumbnail_srcset": thumb["srcset"],
					"genre": w.get("genre", ""),
					"nsfw": w.get("nsfw", False),
					"body": w.get("body", ""),
					"created_at": w.get("created_at", ""),
					"completed_at": w.get("completed_at", ""),
				}
			)

		detail = {
			"screen_name": sn,
			"file": file_key,
			"name": profile.get("name", ""),
			"avatar_url": avatar,
			"header_url": profile.get("header_url", ""),
			"description": profile.get("description", ""),
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
		"Site data written to %s  (%d users, %d detail files)",
		api_dir,
		len(index_entries),
		len(index_entries),
	)