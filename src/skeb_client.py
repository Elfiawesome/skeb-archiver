import re
import random
import time
import asyncio
from typing import AsyncGenerator
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.errors import RequestsError
from .logger import log
from dataclasses import dataclass, field


@dataclass
class FetchRequest:
	endpoint: str
	headers: dict[str, str] = field(default_factory=lambda: {
		"Authorization": "Bearer null",
	})


class RateLimiter:
	def __init__(self, rate_per_sec: float = 3.0):
		self.base_rate = rate_per_sec
		self.current_rate = rate_per_sec
		self.min_rate = max(0.3, rate_per_sec * 0.1)
		self.max_cooldown = 30.0
		self.tokens = rate_per_sec
		self.last_refill = time.monotonic()
		self._lock = asyncio.Lock()
		self._consecutive_429s = 0
		self._cooldown_until = 0.0

	async def acquire(self):
		while True:
			async with self._lock:
				now = time.monotonic()

				if now >= self._cooldown_until:
					elapsed = now - self.last_refill
					self.tokens = min(self.current_rate, self.tokens + elapsed * self.current_rate)
					self.last_refill = now

					if self.tokens >= 1.0:
						self.tokens -= 1.0
						return

					wait = min(5.0, (1.0 - self.tokens) / self.current_rate)
				else:
					wait = self._cooldown_until - now

			await asyncio.sleep(wait)

	def report_429(self):
		self._consecutive_429s += 1
		self.current_rate = max(self.min_rate, self.current_rate * 0.5)
		cooldown = min(self.max_cooldown, 6 * (2 ** min(self._consecutive_429s - 1, 4)))
		self._cooldown_until = time.monotonic() + cooldown
		self.tokens = 0.0

	def report_success(self):
		if self._consecutive_429s > 0:
			self._consecutive_429s = 0
			self._cooldown_until = 0.0
		self.current_rate = min(self.base_rate, self.current_rate * 1.15)


class SkebClient:
	BASE: str = "https://skeb.jp"
	API: str = f"{BASE}/api"
	_COOKIE_RE: re.Pattern = re.compile(r"(request_key=.*?;)")
	BAN_IMAGE_PATTERNS: list[str] = [
		"https://si.imgix.net/867e437f/uploads/origins/a9275de5-30c2-424c-9c23-ac3b9e52da41",
	]

	REQUIRED_WORK_FIELDS: set[str] = set()
	REQUIRED_PROFILE_FIELDS: set[str] = {"screen_name", "id", "skills"}

	def __init__(
		self,
		max_concurrency: int = 10,
		max_retries: int = 3,
		timeout_sec: int = 30,
		paginate_batch_size: int = 10,
		rate_per_sec: float = 3.0,
		impersonate: str = "chrome120",
		max_runtime_sec: float = 0,
	) -> None:
		self.max_concurrency = max_concurrency
		self.max_retries = max_retries
		self.timeout_sec = timeout_sec
		self.paginate_batch_size = paginate_batch_size
		self.rate_per_sec = rate_per_sec
		self.impersonate = impersonate
		self.max_runtime_sec = max_runtime_sec

		self._session: AsyncSession | None = None
		self._semaphore: asyncio.Semaphore | None = None
		self._rate_limiter: RateLimiter | None = None
		self._start_time: float = 0.0

	async def __aenter__(self) -> 'SkebClient':
		self._start_time = time.monotonic()
		self._session = AsyncSession(impersonate=self.impersonate)
		self._rate_limiter = RateLimiter(rate_per_sec=self.rate_per_sec)

		await self._extract_cookie()

		self._semaphore = asyncio.Semaphore(self.max_concurrency)
		log.info("SkebClient ready (impersonate=%s, rate=%.1f/s, concurrency=%d, max_runtime=%s)",
			self.impersonate, self.rate_per_sec, self.max_concurrency,
			f"{self.max_runtime_sec:.0f}s" if self.max_runtime_sec > 0 else "unlimited")
		return self

	async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
		if self._session:
			await self._session.close()
			self._session = None

	async def _extract_cookie(self) -> None:
		for attempt in range(1, 4):
			try:
				r = await self._session.get(self.BASE, timeout=self.timeout_sec)
				log.info("Homepage GET status=%d (attempt %d/3)", r.status_code, attempt)
				body = r.text

				match = self._COOKIE_RE.search(body)
				if match:
					cookie_str = match.group(1).rstrip(";")
					name, _, value = cookie_str.partition("=")
					self._session.cookies.set(name, value, domain="skeb.jp")
					log.info("Cookie extracted [%s=...].", name)
					return

				log.warning("request_key not found in homepage HTML (status=%d).", r.status_code)
				return

			except Exception as e:
				log.warning("Homepage fetch failed (attempt %d/3): %s", attempt, e)
				if attempt < 3:
					await asyncio.sleep(3 * attempt)

		log.warning("Could not extract cookie after 3 attempts. Relying on curl_cffi session cookies.")

	async def _refresh_cookie(self) -> None:
		log.info("Refreshing request_key cookie...")
		try:
			await self._extract_cookie()
		except Exception as e:
			log.error("Cookie refresh failed: %s", e)

	def _is_deadline_exceeded(self) -> bool:
		if self.max_runtime_sec <= 0:
			return False
		return time.monotonic() - self._start_time > self.max_runtime_sec

	async def _fetch_single(self, fr: FetchRequest) -> dict | list:
		url = f"{self.API}/{fr.endpoint}"

		async with self._semaphore:
			for attempt in range(1, self.max_retries + 1):
				if self._is_deadline_exceeded():
					log.info("Max runtime exceeded, cancelling request %s.", url)
					return {
						"error": "Max runtime exceeded",
						"endpoint": fr.endpoint,
						"failed": True,
						"cancelled": True,
						"status_code": None,
					}

				await self._rate_limiter.acquire()

				try:
					response = await self._session.get(
						url,
						headers=fr.headers,
						timeout=self.timeout_sec,
					)

					if response.status_code == 429:
						self._rate_limiter.report_429()
						log.warning("429 on %s (attempt %d/%d, rate=%.1f/s)",
							url, attempt, self.max_retries, self._rate_limiter.current_rate)

						if attempt < self.max_retries:
							backoff = min(60, 2 ** attempt) * (0.8 + 0.4 * random.random())
							log.info("Backing off %.1fs before retry.", backoff)
							await asyncio.sleep(backoff)
							continue

						return {
							"error": "429 Too Many Requests",
							"endpoint": fr.endpoint,
							"failed": True,
							"status_code": 429,
						}

					if response.status_code in (401, 403):
						log.warning("%d on %s, refreshing cookie.", response.status_code, url)
						await self._refresh_cookie()
						if attempt < self.max_retries:
							await asyncio.sleep(1.0)
							continue
						return {
							"error": f"{response.status_code} Forbidden",
							"endpoint": fr.endpoint,
							"failed": True,
							"status_code": response.status_code,
						}

					if not response.ok:
						log.warning("%d on %s (attempt %d/%d)",
							response.status_code, url, attempt, self.max_retries)
						if attempt < self.max_retries:
							backoff = min(30, 2 ** attempt) * (0.8 + 0.4 * random.random())
							await asyncio.sleep(backoff)
							continue
						return {
							"error": f"HTTP {response.status_code}",
							"endpoint": fr.endpoint,
							"failed": True,
							"status_code": response.status_code,
						}

					self._rate_limiter.report_success()

					data = response.json()
					log.info("OK %s" + ("" if attempt == 1 else f" ({attempt}x)"), url)
					return data

				except RequestsError as e:
					status_code = e.response.status_code if e.response is not None else None
					log.error("Error on %s: %s (status=%s)", url, e, status_code)

					if attempt < self.max_retries:
						backoff = min(30, 2 ** attempt) * (0.8 + 0.4 * random.random())
						await asyncio.sleep(backoff)
					else:
						return {
							"error": str(e),
							"endpoint": fr.endpoint,
							"failed": True,
							"status_code": status_code,
						}

				except asyncio.TimeoutError:
					log.error("Timeout on %s (attempt %d/%d)", url, attempt, self.max_retries)
					if attempt < self.max_retries:
						await asyncio.sleep(2 ** attempt)
					else:
						return {
							"error": "Timeout",
							"endpoint": fr.endpoint,
							"failed": True,
							"status_code": None,
						}

	async def fetch_batch(self, endpoints: list[FetchRequest]) -> list[dict | list | None]:
		tasks = [self._fetch_single(endpoint) for endpoint in endpoints]
		return await asyncio.gather(*tasks)

	async def stream_batch(self, endpoints: list[FetchRequest]) -> AsyncGenerator[dict | list | None, None]:
		tasks = [asyncio.create_task(self._fetch_single(endpoint)) for endpoint in endpoints]
		try:
			for coro in asyncio.as_completed(tasks):
				result = await coro
				yield result
		finally:
			for t in tasks:
				if not t.done():
					t.cancel()
			await asyncio.gather(*tasks, return_exceptions=True)

	def _validate_work(self, work: dict) -> bool:
		if not isinstance(work, dict):
			return False
		if self.REQUIRED_WORK_FIELDS:
			if not self.REQUIRED_WORK_FIELDS.issubset(work.keys()):
				missing = self.REQUIRED_WORK_FIELDS - work.keys()
				log.warning("Work missing fields: %s", missing)
				return False
		return True

	def _is_valid_work(self, work: dict) -> bool:
		if not self._validate_work(work):
			return False
		has_images = any(k in work for k in ("thumbnail_image_urls", "censored_thumbnail_image_urls"))
		if has_images and self._is_work_banned_image(work):
			return False
		return True

	def _validate_profile(self, profile: dict) -> bool:
		if not isinstance(profile, dict):
			return False
		if not self.REQUIRED_PROFILE_FIELDS.issubset(profile.keys()):
			missing = self.REQUIRED_PROFILE_FIELDS - profile.keys()
			log.warning("Profile missing fields: %s", missing)
			return False
		return True

	def _is_valid_profile(self, profile: dict) -> bool:
		if not self._validate_profile(profile):
			return False
		if self._is_profile_banned_image(profile):
			return False
		return True

	def _is_profile_banned_image(self, profile: dict) -> bool:
		urls = (
			profile.get("avatar_url", ""),
			profile.get("header_url", ""),
			profile.get("og_image_url", ""),
		)
		return self._contains_banned_url(urls)

	def _is_work_banned_image(self, work: dict) -> bool:
		tiu = work.get("thumbnail_image_urls", {})
		ctiu = work.get("censored_thumbnail_image_urls", {})
		urls = (
			tiu.get("src", ""),
			tiu.get("srcset", ""),
			ctiu.get("src", ""),
			ctiu.get("srcset", ""),
		)
		return self._contains_banned_url(urls)

	def _contains_banned_url(self, urls: tuple) -> bool:
		return any(
			u and any(u.startswith(p) for p in self.BAN_IMAGE_PATTERNS)
			for u in urls
		)

	def _build_paginate_batch(self, *, type_: str, genre: str, offset: int, limit: int) -> list[FetchRequest]:
		batch: list[FetchRequest] = []
		referer = f"{self.BASE}/{type_}?sort=date&genre={genre}"
		for _ in range(self.paginate_batch_size):
			endpoint = f"{type_}?sort=date&genre={genre}&offset={offset}&limit={limit}"
			fr = FetchRequest(endpoint=endpoint)
			fr.headers["Referer"] = referer
			batch.append(fr)
			offset += limit
		return batch

	async def fetch_paginate(
		self,
		type_: str,
		sort: str = "date",
		genre: str = "art",
		max_amt: int = -1,
	) -> AsyncGenerator[dict, None]:
		log.info("Pagination start: type='%s' genre='%s'.", type_, genre)

		offset = 0
		limit = 90
		cur_amt = 0
		consecutive_empty = 0
		max_consecutive_empty = 2

		while True:
			if max_amt > 0 and cur_amt >= max_amt:
				break

			req_batch = self._build_paginate_batch(type_=type_, genre=genre, offset=offset, limit=limit)
			offset += len(req_batch) * limit

			batch_results = await self.fetch_batch(req_batch)
			batch_had_content = False

			for data in batch_results:
				if not isinstance(data, list):
					log.error("Non-list in paginate: %s", type(data).__name__)
					continue

				if len(data) < 1:
					consecutive_empty += 1
					log.info("Empty page (consecutive=%d)", consecutive_empty)
					if consecutive_empty >= max_consecutive_empty:
						log.info("End of pagination (%d empty pages).", consecutive_empty)
						log.info("Pagination done: %d items for '%s'.", cur_amt, type_)
						return
					continue

				consecutive_empty = 0
				batch_had_content = True

				for work in data:
					if not self._is_valid_work(work):
						log.warning("Skipping invalid/banned work in pagination")
						continue

					yield work
					cur_amt += 1

					if max_amt > 0 and cur_amt >= max_amt:
						break

				if max_amt > 0 and cur_amt >= max_amt:
					break

			if not batch_had_content and consecutive_empty >= max_consecutive_empty:
				return

		log.info("Pagination done: %d items for '%s'.", cur_amt, type_)

	async def fetch_profiles(self, screen_names: set[str]) -> AsyncGenerator[dict, None]:
		consecutive_fake = 0

		async for profile in self.stream_batch(
			FetchRequest("users/" + sc) for sc in screen_names
		):
			if not isinstance(profile, dict):
				log.error("Non-dict in fetch_profiles: %s", type(profile).__name__)
				continue

			if profile.get("failed", False):
				yield profile
				continue

			if not self._is_valid_profile(profile):
				consecutive_fake += 1
				log.warning("Fake profile detected (consecutive=%d)", consecutive_fake)

				if consecutive_fake >= 3:
					log.warning("Too many fake profiles, refreshing cookie...")
					await self._refresh_cookie()
					consecutive_fake = 0

				sn = profile.get("screen_name", "unknown")
				yield {
					"error": "Invalid or banned profile",
					"endpoint": f"users/{sn}",
					"failed": True,
					"status_code": None,
				}
				continue

			consecutive_fake = 0
			yield profile
