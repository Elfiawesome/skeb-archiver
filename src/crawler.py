"""
Crawl orchestration.

Discovers users, fetches profiles, gathers works from THREE sources:
	1. Global /works listing  (recent works across all users)
	2. Profile received_works (embedded in the profile response — free)
	3. Per-user /users/{name}/works endpoint (dedicated fetch)

All three are merged with deduplication before persisting.
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
		self._ts = datetime.now(timezone.utc).isoformat()
		self._stats: Dict[str, int] = {
			"works_fetched": 0,
			"users_listed": 0,
			"profiles_ok": 0,
			"profiles_err": 0,
			"profile_works_extracted": 0,
			"user_works_ok": 0,
			"user_works_err": 0,
			"new_works_saved": 0,
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

	def _group_works(self, works: List[Dict]) -> Dict[str, List[Dict]]:
		grouped: Dict[str, List[Dict]] = {}
		for w in works:
			m = self._WORK_RE.search(w.get("path", ""))
			if m:
				grouped.setdefault(m.group(1), []).append(w)
		return grouped

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

	# ── extract works embedded in profiles ───────────────────────

	def _extract_profile_works(
		self,
		profiles: Dict[str, Dict],
		works_by_user: Dict[str, List[Dict]],
	) -> None:
		"""
		Pull ``received_works`` and ``sent_works`` from each profile
		and append them to *works_by_user*.  These are already fetched
		(zero additional API calls).
		"""
		count = 0
		for name, profile in profiles.items():
			for field in ("received_works", "sent_works"):
				embedded = profile.get(field)
				if not isinstance(embedded, list):
					continue
				for w in embedded:
					if w.get("path"):
						works_by_user.setdefault(name, []).append(w)
						count += 1

		self._stats["profile_works_extracted"] = count
		log.info("Extracted %d works from profile data (no extra API calls).", count)

	# ── per-user works fetch ─────────────────────────────────────

	async def _fetch_user_works_batch(
		self, names: List[str]
	) -> Dict[str, List[Dict]]:
		"""
		Fetch works for each user via ``/users/{name}/works``.

		Fetches one page (up to ``page_size`` works) per user.
		Failures are silently skipped (some users may 404).
		"""
		log.info("Fetching per-user works for %d users ...", len(names))
		tasks = [self._client.fetch_user_works(n, limit=self._page) for n in names]
		results = await asyncio.gather(*tasks, return_exceptions=True)

		out: Dict[str, List[Dict]] = {}
		for name, result in zip(names, results):
			if isinstance(result, Exception):
				self._stats["user_works_err"] += 1
				log.debug("User works error %s: %s", name, result)
			elif isinstance(result, list) and result:
				out[name] = result
				self._stats["user_works_ok"] += 1
			else:
				# empty but successful
				self._stats["user_works_ok"] += 1

		log.info(
			"Per-user works: %d OK, %d failed.",
			self._stats["user_works_ok"],
			self._stats["user_works_err"],
		)
		return out

	# ── persist ──────────────────────────────────────────────────

	def _persist(
		self,
		name: str,
		profile: Optional[Dict],
		works: List[Dict],
	) -> None:
		ud = self._store.load(name) or self._store.new_user(name, self._ts)
		if profile:
			self._store.merge_profile(ud, profile, self._ts)
		added = self._store.merge_works(ud, works, self._ts)
		self._stats["new_works_saved"] += added
		self._store.save(ud)
		self._stats["files_written"] += 1

	# ── entry point ──────────────────────────────────────────────

	async def run(self) -> None:
		async with self._client:
			log.info("=" * 60)
			log.info("Crawl started  %s", self._ts)
			log.info("=" * 60)

			# ── 1. Global listings ───────────────────────
			works, users = await asyncio.gather(
				self._paginate(self._client.fetch_works, "works"),
				self._paginate(self._client.fetch_users, "users"),
			)
			self._stats["works_fetched"] = len(works)
			self._stats["users_listed"] = len(users)

			# ── 2. Discover usernames ────────────────────
			names = self._extract_names(works, users)
			log.info("Unique usernames: %d", len(names))

			# ── 3. Fetch full profiles ───────────────────
			profiles = await self._fetch_profiles(names)

			# ── 4. Gather works from ALL sources ─────────
			works_by_user = self._group_works(works)

			# 4a. Works embedded in profile responses (free)
			self._extract_profile_works(profiles, works_by_user)

			# 4b. Dedicated per-user works API
			all_known = sorted(set(profiles) | set(works_by_user))
			user_works_map = await self._fetch_user_works_batch(all_known)
			for uname, wks in user_works_map.items():
				works_by_user.setdefault(uname, []).extend(wks)

			# ── 5. Merge & persist ───────────────────────
			final_names = sorted(set(profiles) | set(works_by_user))
			for uname in final_names:
				self._persist(
					uname,
					profiles.get(uname),
					works_by_user.get(uname, []),
				)

			self._log_summary()

	def _log_summary(self) -> None:
		log.info("=" * 60)
		log.info("  CRAWL SUMMARY")
		log.info("-" * 60)
		for key, val in self._stats.items():
			log.info("  %-26s : %d", key, val)
		log.info("=" * 60)