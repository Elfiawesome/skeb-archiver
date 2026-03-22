"""
Crawl orchestration.

Discovers users via global listings, fetches full profiles.
Works data lives inside the profile response (``received_works``,
``sent_works``) — we do NOT store a separate works list.
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Callable, Coroutine, Dict, List, Optional, Set

from .client import SkebClient
from .limiter import RateLimiter
from .logger import log
from .store import DataStore


class SkebCrawler:
	_WORK_RE = re.compile(r"/@([^/]+)/works/(\d+)")

	def __init__(
		self,
		data_dir: str = "skeb",
		concurrency: int = 10,
		request_delay: float = 0.05,
		page_size: int = 90,
		pages_per_batch: int = 10,
		max_items: int = -1,
		genre: str = "art",
		retries: int = 3,
	) -> None:
		self._store = DataStore(data_dir)
		self._rl = RateLimiter(concurrency, request_delay)
		self._client = SkebClient(
			self._rl,
			max_retries=retries,
			max_connections=concurrency * 2,
		)
		self._page = page_size
		self._batch = pages_per_batch
		self._cap = max_items
		self._genre = genre
		self._ts = datetime.now(timezone.utc).timestamp()
		self._stats: Dict[str, int] = {
			"global_works_fetched": 0,
			"users_listed": 0,
			"profiles_ok": 0,
			"profiles_err": 0,
			"files_written": 0,
		}

	# ── paginated listing ────────────────────────────────────────

	async def _paginate(
		self,
		fetcher: Callable[..., Coroutine],
		label: str,
	) -> List[Dict]:
		items: List[Dict] = []
		page = 0

		while True:
			log.info("[%s] pages %d–%d", label, page, page + self._batch - 1)
			tasks = [
				fetcher(
					offset=(page + i) * self._page,
					limit=self._page,
					genre=self._genre,
				)
				for i in range(self._batch)
			]
			results = await asyncio.gather(*tasks, return_exceptions=True)

			added = 0
			exhausted = False
			for r in results:
				if isinstance(r, Exception):
					log.error("[%s] page error: %s", label, r)
					continue
				if not r:
					exhausted = True
					break
				items.extend(r)
				added += len(r)

			page += self._batch
			log.info("[%s] +%d  (total %d)", label, added, len(items))

			if exhausted:
				log.info("[%s] endpoint exhausted.", label)
				break
			if 0 < self._cap <= len(items):
				log.info("[%s] cap reached (%d).", label, self._cap)
				break

		return items

	# ── helpers ──────────────────────────────────────────────────

	def _extract_names(
		self, works: List[Dict], users: List[Dict]
	) -> Set[str]:
		names: Set[str] = set()
		for w in works:
			m = self._WORK_RE.search(w.get("path", ""))
			if m:
				names.add(m.group(1))
		for u in users:
			sn = u.get("screen_name")
			if sn:
				names.add(sn)
		return names

	# ── profile fetch ────────────────────────────────────────────

	async def _fetch_profiles(self, names: Set[str]) -> Dict[str, Dict]:
		log.info("Fetching %d profiles ...", len(names))
		ordered = sorted(names)
		tasks = [self._client.fetch_profile(n) for n in ordered]
		results = await asyncio.gather(*tasks, return_exceptions=True)

		profiles: Dict[str, Dict] = {}
		for name, result in zip(ordered, results):
			if isinstance(result, Exception):
				self._stats["profiles_err"] += 1
				log.debug("Profile error %s: %s", name, result)
			elif result and "screen_name" in result:
				profiles[result["screen_name"]] = result
				self._stats["profiles_ok"] += 1

		log.info(
			"Profiles: %d OK, %d failed.",
			self._stats["profiles_ok"],
			self._stats["profiles_err"],
		)
		return profiles

	# ── persist ──────────────────────────────────────────────────

	def _persist(self, name: str, profile: Dict) -> None:
		ud = self._store.load(name) or self._store.new_user(name, self._ts)
		self._store.merge_profile(ud, profile, self._ts)
		self._store.save(ud)
		self._stats["files_written"] += 1

	# ── entry point ──────────────────────────────────────────────

	async def run(self) -> None:
		async with self._client:
			log.info("=" * 60)
			log.info("Crawl started  %s", self._ts)
			log.info("=" * 60)

			# 1. Global listings (to discover usernames)
			works, users = await asyncio.gather(
				self._paginate(self._client.fetch_works, "works"),
				self._paginate(self._client.fetch_users, "users"),
			)
			self._stats["global_works_fetched"] = len(works)
			self._stats["users_listed"] = len(users)

			# 2. Discover usernames
			names = self._extract_names(works, users)
			log.info("Unique usernames: %d", len(names))

			# 3. Fetch full profiles (includes received_works)
			profiles = await self._fetch_profiles(names)

			# 4. Persist
			for uname, profile in sorted(profiles.items()):
				self._persist(uname, profile)

			self._log_summary()

	def _log_summary(self) -> None:
		log.info("=" * 60)
		log.info("  CRAWL SUMMARY")
		log.info("-" * 60)
		for key, val in self._stats.items():
			log.info("  %-30s : %d", key, val)
		log.info("=" * 60)