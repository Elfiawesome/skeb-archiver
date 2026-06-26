import re
import aiohttp
import asyncio
from typing import AsyncGenerator
from .logger import log
from dataclasses import dataclass, field


@dataclass
class FetchRequest:
	endpoint: str
	headers: dict[str] = field(default_factory=lambda: {
		"Authorization": "Bearer null",
		# "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
	})

class SkebClient():
	BASE: str = "https://skeb.jp"
	API: str = f"{BASE}/api"
	_COOKIE_RE: re.Pattern = re.compile(r"(request_key=.*?;)")
	
	def __init__(self) -> None:
		self.max_sync_request: int = 10
		self.max_retries: int = 3
		self.timeout_sec: int = 30
		self.rate_limit_sleep: float = 0.05

		self._session: aiohttp.ClientSession | None = None
		self._semaphore: asyncio.Semaphore | None = None

		self._cookie: str | None = None
	
	async def __aenter__(self) -> 'SkebClient':
		timeout = aiohttp.ClientTimeout(total=self.timeout_sec)
		self._session = aiohttp.ClientSession(timeout=timeout)
		
		async with self._session.get(self.BASE) as r:
			body = await r.text()
			match = self._COOKIE_RE.search(body)
			if match:
				self._cookie = match.group(1)
				log.info(f"Client cookie found [{self._cookie}].")
			else:
				log.warning("Could not extract request_key cookie.")

		
		self._semaphore = asyncio.Semaphore(self.max_sync_request)
		log.info("Initialized Skeb Client.")
		return self

	async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
		if self._session:
			await self._session.close()
		self._cookie = None

	async def _fetch_single(self, fr: FetchRequest) -> dict | list:
		url = f"{self.API}/{fr.endpoint}"
		fr.headers["Cookie"]= self._cookie

		async with self._semaphore:
			await asyncio.sleep(self.rate_limit_sleep)
			for attempt in range(1, self.max_retries + 1):
				try:
					async with self._session.get(url, headers=fr.headers) as response:
						log.info(f"Requesting {url}" + ("" if attempt == 1 else f"({attempt}x)"))
						response.raise_for_status()
						return await response.json()
						
				except (aiohttp.ClientError, asyncio.TimeoutError) as e:
					status_code: int | None = None
					if isinstance(e, aiohttp.ClientResponseError): status_code = e.status
					
					if (attempt == self.max_retries) or (status_code == 429):
						log.error(f"Error on requesting {url} with error {e}")
						return {"error": e, "endpoint": fr.endpoint, "failed": True, "status_code": status_code}
					
					await asyncio.sleep(1 * attempt)

	async def fetch_batch(self, endpoints: list[FetchRequest]) -> list[dict | list | None]:
		tasks = [self._fetch_single(endpoint) for endpoint in endpoints]
		return await asyncio.gather(*tasks)

	async def stream_batch(self, endpoints: list[FetchRequest]) -> AsyncGenerator[dict | list | None , None]:
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


	async def fetch_paginate(self, type: str, sort: str = "date", genre: str = "art", max_amt: int = -1) -> AsyncGenerator[dict, None]:
		log.info(f"Start pagination for work type '{type}' and genre '{genre}'.")
		paginate_per_loop = 10
		
		offset = 0
		limit = 90
		
		no_more_pagination: bool = False
		cur_amt: int = 0
		while True:
			req_batch: list[FetchRequest] = []
			for i in range(paginate_per_loop):
				fr = FetchRequest(endpoint=f"{type}?sort=date&genre={genre}&offset={offset}&limit={limit}")
				fr.headers["Referer"] = f"{self.BASE}/{type}?sort=date&genre={genre}"
				req_batch.append(fr)
				offset += limit
			
			for data in await self.fetch_batch(req_batch):
				if not isinstance(data, list):
					log.error(f"Received a none list type during fetch_paginate: {data}")
					continue

				if (len(data) < 1) or (cur_amt > max_amt and max_amt > 0):
					no_more_pagination = True
					break
				
				for work in data:
					yield work
					cur_amt += 1
			
			if no_more_pagination:
				log.info(f"Completed pagination for work type '{type}' and genre '{genre}' for a total of {cur_amt} items.")
				break
	
	async def fetch_profiles(self, screen_names: set[str]) -> AsyncGenerator[dict, None]:
		async for profile in self.stream_batch("users/" + sc for sc in screen_names):
			if not isinstance(profile, dict):
				log.error(f"Received a non-dict type during fetch_profiles: {profile}")
				continue
			yield profile
