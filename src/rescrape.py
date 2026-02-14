"""
Re-scrape every user already stored in ``skeb/`` to refresh
profiles and prices.

* 200 OK  → profile updated, ``missing`` cleared if it was set.
* 404/410 → ``missing`` set to ``true``.
* Other errors → logged, user left unchanged.

Usage::

	python run_rescrape.py
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict

import aiohttp

from .client import SkebClient
from .limiter import RateLimiter
from .logger import log
from .store import DataStore


class Rescraper:
	def __init__(
		self,
		data_dir: str = "skeb",
		concurrency: int = 10,
		request_delay: float = 0.05,
		retries: int = 3,
	) -> None:
		self._store = DataStore(data_dir)
		self._rl = RateLimiter(concurrency, request_delay)
		self._client = SkebClient(
			self._rl,
			max_retries=retries,
			max_connections=concurrency * 2,
		)
		self._ts = datetime.now(timezone.utc).isoformat()
		self._stats: Dict[str, int] = {
			"total": 0,
			"updated": 0,
			"missing_new": 0,
			"missing_still": 0,
			"recovered": 0,
			"errors": 0,
		}

	async def _fetch_safe(self, name: str):
		"""
		Returns:
			dict  – successful profile
			None  – user gone (404 / 410)
			Exception – other error
		"""
		try:
			return await self._client.fetch_profile(name)
		except aiohttp.ClientResponseError as exc:
			if exc.status in (404, 410):
				return None
			return exc
		except Exception as exc:
			return exc

	async def run(self) -> None:
		async with self._client:
			log.info("=" * 60)
			log.info("Rescrape started  %s", self._ts)
			log.info("=" * 60)

			names = self._store.list_screen_names()
			self._stats["total"] = len(names)
			log.info("Users to rescrape: %d", len(names))

			if not names:
				log.info("No existing users. Nothing to do.")
				return

			# Fire all fetches — the RateLimiter semaphore
			# controls how many are actually in-flight.
			log.info("Fetching profiles ...")
			tasks = [self._fetch_safe(n) for n in names]
			results = await asyncio.gather(*tasks)

			for name, result in zip(names, results):
				user = self._store.load(name)
				if user is None:
					log.warning("File unreadable for %s, skipping", name)
					continue

				was_missing = user.get("missing", False)

				# ── error ────────────────────────────────
				if isinstance(result, Exception):
					log.warning("Error for %s: %s", name, result)
					self._stats["errors"] += 1
					continue                     # leave user unchanged

				# ── user gone ────────────────────────────
				if result is None:
					user["missing"] = True
					user["last_updated"] = self._ts
					if was_missing:
						self._stats["missing_still"] += 1
					else:
						self._stats["missing_new"] += 1
						log.info("Marked missing: %s", name)

				# ── success ──────────────────────────────
				else:
					self._store.merge_profile(user, result, self._ts)
					if was_missing:
						user["missing"] = False
						self._stats["recovered"] += 1
						log.info("Recovered: %s", name)
					self._stats["updated"] += 1

				self._store.save(user)

			self._log_summary()

	def _log_summary(self) -> None:
		log.info("=" * 60)
		log.info("  RESCRAPE SUMMARY")
		log.info("-" * 60)
		for key, val in self._stats.items():
			log.info("  %-20s : %d", key, val)
		log.info("=" * 60)