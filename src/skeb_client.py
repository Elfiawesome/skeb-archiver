import re
import aiohttp
import asyncio
from typing import AsyncGenerator
from .logger import log

class SkebClient():
	BASE: str = "https://skeb.jp"
	API: str = f"{BASE}/api"
	_COOKIE_RE: re.Pattern = re.compile(r"(request_key=.*?;)")
	
	def __init__(self) -> None:
		self.max_sync_request: int = 5
		self.max_retries: int = 3
		self.timeout_sec: int = 30

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

	async def _fetch_single(self, endpoint: str, **kwargs) -> dict:
		url = f"{self.API}/{endpoint}"
		headers = {"Authorization": "Bearer null", "Cookie": self._cookie}

		async with self._semaphore:
			for attempt in range(1, self.max_retries + 1):
				try:
					async with self._session.get(url, headers=headers, **kwargs) as response:
						log.info(f"Requesting {url}...")
						response.raise_for_status()
						return await response.json()
						
				except (aiohttp.ClientError, asyncio.TimeoutError) as e:
					if attempt == self.max_retries:
						return {"error": str(e), "endpoint": endpoint, "failed": True}
					
					await asyncio.sleep(1 * attempt)

	async def fetch_batch(self, endpoints: list[str]) -> list[dict | None]:
		tasks = [self._fetch_single(endpoint) for endpoint in endpoints]
		return await asyncio.gather(*tasks)

	async def stream_batch(self, endpoints: list[str]) -> AsyncGenerator[dict | None , None]:
		tasks = [asyncio.create_task(self._fetch_single(endpoint)) for endpoint in endpoints]
		
		for coro in asyncio.as_completed(tasks):
			result = await coro
			yield result


	async def fetch_paginate(self, type: str, sort: str = "date", genre: str = "art", max_amt: int = -1) -> AsyncGenerator[dict, None]:
		log.info(f"Start pagination for work type '{type}' and genre '{genre}'.")
		paginate_per_loop = 2
		
		offset = 0
		limit = 90
		
		no_more_pagination: bool = False
		cur_amt: int = 0
		while True:
			req_batch: list[str] = []
			for i in range(paginate_per_loop):
				req_batch.append(f"{type}?sort=date&genre={genre}&offset={offset}&limit={limit}")
				offset += limit
			
			async for data in self.stream_batch(req_batch):
				if (len(data) < 1) or (cur_amt > max_amt and max_amt > 0):
					no_more_pagination = True
					break
				
				for work in data:
					yield work
					cur_amt += 1
			
			if no_more_pagination:
				log.info(f"Completed pagination for work type '{type}' and genre '{genre} for a total of {cur_amt} items.")
				break
	
	async def fetch_profiles(self, screen_names: list[str]) -> AsyncGenerator[dict, None]:
		async for profile in self.stream_batch("users/" + sc for sc in screen_names):
			yield profile