"""
Static-site data generator.

Reads raw user files from ``data_dir`` and writes:
	<output_dir>/api/index.json             metadata + known_flags
	<output_dir>/api/pages/<n>.json         paginated user entries
	<output_dir>/api/users/<file>.json      full detail per user
"""

import json
import math
import gzip
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from .logger import log
from .store import DataStore, SYSTEM_KEYS

_PLATFORM_URLS = {
	"pixiv_id":    ("Pixiv",    "https://www.pixiv.net/users/{}"),
	"nijie_id":    ("Nijie",    "https://nijie.info/members.php?id={}"),
	"booth_id":    ("BOOTH",    "https://{}.booth.pm"),
	"fantia_id":   ("Fantia",   "https://fantia.jp/fanclubs/{}"),
	"fanbox_id":   ("Fanbox",   "https://{}.fanbox.cc"),
	"youtube_id":  ("YouTube",  "https://youtube.com/channel/{}"),
	"patreon_id":  ("Patreon",  "https://patreon.com/{}"),
	"skima_id":    ("SKIMA",    "https://skima.jp/profile?id={}"),
	"coconala_id": ("Coconala", "https://coconala.com/users/{}"),
	"dlsite_id":   ("DLsite",
					"https://www.dlsite.com/home/circle/profile/=/maker_id/{}"),
	"fanza_id":    ("FANZA",
					"https://www.dmm.co.jp/dc/doujin/-/detail/=/keyword={}"),
}

PAGE_SIZE = 20000


# ── flags ────────────────────────────────────────────────────

def _extract_flags(user: Dict) -> Dict[str, Any]:
	"""Return all non-system keys (custom flags)."""
	return {k: v for k, v in user.items() if k not in SYSTEM_KEYS}


# ── thumbnail helpers ────────────────────────────────────────

def _extract_thumbnail(work: Dict) -> Dict[str, str]:
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


def _latest_thumbnail_urls(works: List[Dict], max_count: int = 4) -> List[str]:
	urls: List[str] = []
	for w in works:
		thumb = _extract_thumbnail(w)
		if thumb["src"]:
			urls.append(_pick_best_url(thumb["srcset"], thumb["src"]))
			if len(urls) >= max_count:
				break
	return urls


# ── link helpers ─────────────────────────────────────────────

def _extract_links(profile: Dict) -> List[Dict[str, str]]:
	links: List[Dict[str, str]] = []
	seen: set = set()
	for sl in profile.get("user_service_links") or []:
		url = sl.get("url", "")
		if url and url not in seen:
			links.append({
				"label": sl.get("provider", "link").capitalize(),
				"url": url,
				"name": sl.get("screen_name", ""),
			})
			seen.add(url)
	standalone = profile.get("url", "")
	if standalone and standalone not in seen:
		links.append({"label": "Website", "url": standalone, "name": ""})
		seen.add(standalone)
	for key, (label, tmpl) in _PLATFORM_URLS.items():
		pid = profile.get(key)
		if pid:
			url = tmpl.format(pid)
			if url not in seen:
				links.append({"label": label, "url": url, "name": str(pid)})
				seen.add(url)
	return links


# ── price helpers ────────────────────────────────────────────

def _current_prices(ph: Dict[str, list]) -> Dict[str, Any]:
	return {g: e[-1].get("amount") for g, e in ph.items() if e}


def _price_ranges(ph: Dict[str, list]) -> Dict[str, Dict[str, Any]]:
	out: Dict[str, Dict[str, Any]] = {}
	for genre, entries in ph.items():
		amounts = [e["amount"] for e in entries if e.get("amount") is not None]
		if amounts:
			out[genre] = {"min": min(amounts), "max": max(amounts)}
	return out


def _get_received_works(profile: Dict) -> List[Dict]:
	rw = profile.get("received_works")
	return rw if isinstance(rw, list) else []


def _true_works_count(profile: Dict) -> int:
	c = profile.get("received_works_count")
	if isinstance(c, int):
		return c
	rw = profile.get("received_works")
	return len(rw) if isinstance(rw, list) else 0


# ── main entry point ─────────────────────────────────────────

def generate_data(
	data_dir: str = "docs/skeb",
	output_dir: str = "docs",
	page_size: int = PAGE_SIZE,
) -> None:
	store = DataStore(data_dir)
	all_users = store.load_all()

	api_dir = Path(output_dir) / "api"
	# users_dir = api_dir / "users"
	pages_dir = api_dir / "pages"
	# users_dir.mkdir(parents=True, exist_ok=True)
	pages_dir.mkdir(parents=True, exist_ok=True)

	index_entries: List[Dict[str, Any]] = []
	all_flag_names: Set[str] = set()

	for u in all_users:
		sn = u.get("screen_name", "")
		if not sn:
			continue

		ph = u.get("price_history", {})
		profile = u.get("profile", {})
		avatar = profile.get("avatar_url", "")
		file_key = DataStore.username_safe(sn)
		works = _get_received_works(profile)
		total_works = _true_works_count(profile)
		flags = _extract_flags(u)
		acceptable = bool(profile.get("acceptable", False))

		# track discovered flag names
		all_flag_names.update(flags.keys())

		# ── lightweight index entry ──────────────────────
		index_entries.append(
			{
				"screen_name": sn,
				"file": file_key,
				"avatar_url": avatar,
				"total_works": total_works,
				"first_seen": u.get("first_seen", ""),
				"last_updated": u.get("last_updated", ""),
				"current_prices": _current_prices(ph),
				"price_range": _price_ranges(ph),
				"latest_thumbnails": _latest_thumbnail_urls(works, 4),
				"flags": flags,
				"acceptable": acceptable,
			}
		)

		# # ── full detail file ─────────────────────────────
		# works_out: List[Dict[str, Any]] = []
		# for w in works:
		# 	thumb = _extract_thumbnail(w)
		# 	works_out.append(
		# 		{
		# 			"path": w.get("path", ""),
		# 			"thumbnail_src": thumb["src"],
		# 			"thumbnail_srcset": thumb["srcset"],
		# 			"genre": w.get("genre", ""),
		# 			"nsfw": w.get("nsfw", False),
		# 			"body": w.get("body", ""),
		# 			"created_at": w.get("created_at", ""),
		# 			"completed_at": w.get("completed_at", ""),
		# 		}
		# 	)

		# detail = {
		# 	"screen_name": sn,
		# 	"file": file_key,
		# 	"name": profile.get("name", ""),
		# 	"avatar_url": avatar,
		# 	"header_url": profile.get("header_url", ""),
		# 	"description": profile.get("description", ""),
		# 	"total_works": total_works,
		# 	"scraped_works": len(works),
		# 	"first_seen": u.get("first_seen", ""),
		# 	"last_updated": u.get("last_updated", ""),
		# 	"price_history": ph,
		# 	"current_prices": _current_prices(ph),
		# 	"price_range": _price_ranges(ph),
		# 	"links": _extract_links(profile),
		# 	"flags": flags,
		# 	"acceptable": acceptable,
		# 	"works": works_out,
		# }

		# with (users_dir / f"{file_key}.json").open("w", encoding="utf-8") as fh:
		# 	json.dump(detail, fh, ensure_ascii=False)

	# ── paginated index files ────────────────────────────
	total_pages = max(1, math.ceil(len(index_entries) / page_size))
	for page_num in range(total_pages):
		start = page_num * page_size
		page_data = {"page": page_num, "users": index_entries[start:start + page_size]}
		with (pages_dir / f"{page_num}.json.gz").open("wb") as f_out, gzip.open(f_out, "wt", encoding="utf-8") as fh:
			json.dump(page_data, fh, ensure_ascii=False)

	# ── master index ─────────────────────────────────────
	index = {
		"generated_at": datetime.now(timezone.utc).timestamp(),
		"user_count": len(index_entries),
		"page_size": page_size,
		"total_pages": total_pages,
		"known_flags": sorted(all_flag_names),
	}
	with (api_dir / "index.json").open("w", encoding="utf-8") as fh:
		json.dump(index, fh, ensure_ascii=False)

	log.info(
		"Site data: %d users, %d pages, flags %s -> %s",
		len(index_entries), total_pages, sorted(all_flag_names), api_dir,
	)