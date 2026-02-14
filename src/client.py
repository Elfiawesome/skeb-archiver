"""Async HTTP client for the Skeb public API."""

import asyncio
import re
from typing import Any, Dict, List, Optional

import aiohttp

from .limiter import RateLimiter
from .logger import log


class SkebClient:
	BASE = "https://skeb.jp"
	API = f"{BASE}/api"
	_COOKIE_RE = re.compile(r"(request_key=.*?;)")

	def __init__(
		self,
		limiter: RateLimiter,
		*,
		max_retries: int = 3,
		timeout_sec: int = 30,
		max_connections: int = 20,
	) -> None:
		self._rl = limiter
		self._retries = max_retries
		self._timeout = aiohttp.ClientTimeout(total=timeout_sec)
		self._max_conn = max_connections
		self._session: Optional[aiohttp.ClientSession] = None
		self._cookie = ""

	# ── lifecycle ────────────────────────────────────────────────

	async def open(self) -> None:
		connector = aiohttp.TCPConnector(limit=self._max_conn)
		self._session = aiohttp.ClientSession(
			connector=connector, timeout=self._timeout
		)
		log.info("Fetching session cookie ...")
		async with self._session.get(self.BASE) as resp:
			body = await resp.text()
		match = self._COOKIE_RE.search(body)
		if match:
			self._cookie = match.group(1)
			log.info("Session cookie obtained.")
		else:
			log.warning("Could not extract request_key cookie.")

	async def close(self) -> None:
		if self._session:
			await self._session.close()
			self._session = None
			log.info("HTTP session closed.")

	async def __aenter__(self):
		await self.open()
		return self

	async def __aexit__(self, *_exc):
		await self.close()

	# ── GET with retries ─────────────────────────────────────────

	async def _get(self, url: str) -> Any:
		headers = {"Authorization": "Bearer null", "Cookie": self._cookie}
		last_exc: Optional[Exception] = None
		for attempt in range(1, self._retries + 1):
			try:
				async with self._rl:
					log.debug("GET %s  (attempt %d)", url, attempt)
					async with self._session.get(url, headers=headers) as resp:
						resp.raise_for_status()
						return await resp.json()
			except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
				last_exc = exc
				if attempt < self._retries:
					wait = 2 ** attempt
					log.warning(
						"Retry %d/%d for %s – %s (backoff %ds)",
						attempt, self._retries, url, exc, wait,
					)
					await asyncio.sleep(wait)
		raise last_exc  # type: ignore[misc]

	# ── endpoint helpers ─────────────────────────────────────────

	async def fetch_works(
		self, *, offset: int = 0, limit: int = 90, genre: str = "art"
	) -> List[Dict]:
		url = (
			f"{self.API}/works"
			f"?sort=date&genre={genre}&offset={offset}&limit={limit}"
		)
		return await self._get(url)

	async def fetch_users(
		self, *, offset: int = 0, limit: int = 90, genre: str = "art"
	) -> List[Dict]:
		url = (
			f"{self.API}/users"
			f"?sort=date&genre={genre}&offset={offset}&limit={limit}"
		)
		return await self._get(url)

	async def fetch_profile(self, screen_name: str) -> Dict:
		return await self._get(f"{self.API}/users/{screen_name}")

	async def fetch_user_works(
		self, screen_name: str, *, offset: int = 0, limit: int = 90
	) -> List[Dict]:
		"""Fetch works for a specific user (received commissions)."""
		url = (
			f"{self.API}/users/{screen_name}/works"
			f"?sort=date&offset={offset}&limit={limit}"
		)
		return await self._get(url)