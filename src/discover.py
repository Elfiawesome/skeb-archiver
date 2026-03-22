"""
Discover new users from similar_creators in existing profiles.

Scans all stored user files, collects ``similar_creators`` screen names,
filters out those already stored, and fetches profiles for the rest.

Usage::

	python run.py discover
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Set
import itertools

import aiohttp

from .client import SkebClient
from .limiter import RateLimiter
from .logger import log
from .store import DataStore


class Discoverer:
	"""Fetch profiles for similar_creators not yet in the store."""

	def __init__(
		self,
		data_dir: str = "docs/skeb",
		concurrency: int = 10,
		request_delay: float = 0.05,
		retries: int = 3,
		max_users: int = -1,
	) -> None:
		self._store = DataStore(data_dir)
		self._rl = RateLimiter(concurrency, request_delay)
		self._client = SkebClient(
			self._rl,
			max_retries=retries,
			max_connections=concurrency * 2,
		)
		self.max_users = max_users
		self._ts = datetime.now(timezone.utc).timestamp()
		self._stats: Dict[str, int] = {
			"existing_users": 0,
			"candidates": 0,
			"new_to_fetch": 0,
			"profiles_ok": 0,
			"profiles_gone": 0,
			"errors": 0,
		}

	# ── collection ───────────────────────────────────────────────

	def _collect_new_names(self) -> Set[str]:
		"""Return similar_creators screen names not already stored."""
		all_users = self._store.load_all()
		existing: Set[str] = set()
		candidates: Set[str] = set()

		for u in all_users:
			sn = u.get("screen_name")
			if sn:
				existing.add(sn)

			profile = u.get("profile") or {}
			for sc in profile.get("similar_creators") or []:
				csn = sc.get("screen_name")
				if csn:
					candidates.add(csn)

		self._stats["existing_users"] = len(existing)
		self._stats["candidates"] = len(candidates)

		new_names = candidates - existing
		if self.max_users!=-1:
			new_names = set(itertools.islice(new_names, self.max_users))
		
		self._stats["new_to_fetch"] = len(new_names)
		return new_names

	# ── safe fetch ───────────────────────────────────────────────

	async def _fetch_safe(self, name: str):
		"""
		Returns:
			dict	  – successful profile
			None	  – user gone (404 / 410)
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

	# ── entry point ──────────────────────────────────────────────

	async def run(self) -> None:
		async with self._client:
			log.info("=" * 60)
			log.info("Discover started  %s", self._ts)
			log.info("=" * 60)

			new_names = self._collect_new_names()
			log.info(
				"Existing: %d | Candidates: %d | New to fetch: %d",
				self._stats["existing_users"],
				self._stats["candidates"],
				self._stats["new_to_fetch"],
			)

			if not new_names:
				log.info("No new users to discover.")
				self._log_summary()
				return

			ordered = sorted(new_names)
			log.info("Fetching %d new profiles ...", len(ordered))
			tasks = [self._fetch_safe(n) for n in ordered]
			results = await asyncio.gather(*tasks)

			for name, result in zip(ordered, results):
				if isinstance(result, Exception):
					log.warning("Error for %s: %s", name, result)
					self._stats["errors"] += 1
					continue

				if result is None:
					self._stats["profiles_gone"] += 1
					log.debug("User gone: %s", name)
					continue

				if result and "screen_name" in result:
					sn = result["screen_name"]
					user = self._store.new_user(sn, self._ts)
					self._store.merge_profile(user, result, self._ts)
					self._store.save(user)
					self._stats["profiles_ok"] += 1

			self._log_summary()

	def _log_summary(self) -> None:
		log.info("=" * 60)
		log.info("  DISCOVER SUMMARY")
		log.info("-" * 60)
		for key, val in self._stats.items():
			log.info("  %-20s : %d", key, val)
		log.info("=" * 60)