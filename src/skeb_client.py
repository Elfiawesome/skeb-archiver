import re
import random
import aiohttp
import asyncio
import ssl
from typing import AsyncGenerator
from .logger import log
from dataclasses import dataclass, field


@dataclass
class FetchRequest:
	endpoint: str
	headers: dict[str, str] = field(default_factory=lambda: {
		"Authorization": "Bearer null",
	})

class SkebClient:
	BASE: str = "https://skeb.jp"
	API: str = f"{BASE}/api"
	DEFAULT_OPENSSL_CIPHER = "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS"
	_COOKIE_RE: re.Pattern = re.compile(r"(request_key=.*?;)")
	BAN_IMAGE_URL: str = "https://si.imgix.net/867e437f/uploads/origins/a9275de5-30c2-424c-9c23-ac3b9e52da41"

	def __init__(
		self,
		max_concurrency: int = 10,
		max_retries: int = 3,
		timeout_sec: int = 30,
		rate_limit_sleep_min: float = 0.02,
		rate_limit_sleep_max: float = 0.10,
		paginate_batch_size: int = 10,
	) -> None:
		self.max_concurrency = max_concurrency
		self.max_retries = max_retries
		self.timeout_sec = timeout_sec
		self.rate_limit_sleep_min = rate_limit_sleep_min
		self.rate_limit_sleep_max = rate_limit_sleep_max
		self.paginate_batch_size = paginate_batch_size

		self._session: aiohttp.ClientSession | None = None
		self._semaphore: asyncio.Semaphore | None = None
		self._cookie: str | None = None

	async def __aenter__(self) -> 'SkebClient':
		timeout = aiohttp.ClientTimeout(total=self.timeout_sec)
		ssl_ctx = ssl.create_default_context()
		ssl_ctx.set_ciphers(self.DEFAULT_OPENSSL_CIPHER)
		connector = aiohttp.TCPConnector(ssl=ssl_ctx)
		self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)

		async with self._session.get(self.BASE) as r:
			body = await r.text()
			match = self._COOKIE_RE.search(body)
			if match:
				self._cookie = match.group(1)
				log.info(f"Client cookie found [{self._cookie}].")
			else:
				log.warning("Could not extract request_key cookie.")

		self._semaphore = asyncio.Semaphore(self.max_concurrency)
		log.info("Initialized Skeb Client.")
		return self

	async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
		if self._session:
			await self._session.close()
		self._cookie = None

	async def _fetch_single(self, fr: FetchRequest) -> dict | list:
		url = f"{self.API}/{fr.endpoint}"
		fr.headers["Cookie"] = self._cookie

		async with self._semaphore:
			await asyncio.sleep(random.uniform(self.rate_limit_sleep_min, self.rate_limit_sleep_max))
			for attempt in range(1, self.max_retries + 1):
				try:
					async with self._session.get(url, headers=fr.headers) as response:
						log.info(f"Requesting {url}" + ("" if attempt == 1 else f" ({attempt}x)"))
						response.raise_for_status()
						return await response.json()

				except (aiohttp.ClientError, asyncio.TimeoutError) as e:
					status_code: int | None = None
					if isinstance(e, aiohttp.ClientResponseError):
						status_code = e.status

					if (attempt == self.max_retries) or (status_code == 429):
						log.error(f"Error on requesting {url} with error {e}")
						return {"error": e, "endpoint": fr.endpoint, "failed": True, "status_code": status_code}

					await asyncio.sleep(1 * attempt)

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

	def _is_banned_image(self, work: dict) -> bool:
		tiu = work.get("thumbnail_image_urls", {})
		ctiu = work.get("consored_thumbnail_image_urls", {})
		urls = (
			tiu.get("src", ""),
			tiu.get("srcset", ""),
			ctiu.get("src", ""),
			ctiu.get("srcset", ""),
		)
		return any(u.startswith(self.BAN_IMAGE_URL) for u in urls)

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
		log.info(f"Start pagination for work type '{type_}' and genre '{genre}'.")

		offset = 0
		limit = 90
		finished: bool = False
		cur_amt: int = 0

		while True:
			req_batch = self._build_paginate_batch(type_=type_, genre=genre, offset=offset, limit=limit)
			offset += len(req_batch) * limit

			for data in await self.fetch_batch(req_batch):
				if not isinstance(data, list):
					log.error(f"Received a non-list type during fetch_paginate: {data}")
					continue

				if (len(data) < 1) or (cur_amt > max_amt and max_amt > 0):
					finished = True
					break

				for work in data:
					if self._is_banned_image(work):
						log.error("paginate work page received is a blur banned image: " + str(work))
						continue

					yield work
					cur_amt += 1

			if finished:
				log.info(f"Completed pagination for work type '{type_}' and genre '{genre}' for a total of {cur_amt} items.")
				break

	async def fetch_profiles(self, screen_names: set[str]) -> AsyncGenerator[dict, None]:
		async for profile in self.stream_batch(FetchRequest("users/" + sc) for sc in screen_names):
			if not isinstance(profile, dict):
				log.error(f"Received a non-dict type during fetch_profiles: {profile}")
				continue
			yield profile
