"""Async concurrency limiter (semaphore + per-slot delay)."""

import asyncio


class RateLimiter:
	"""Controls how many requests can be in-flight at once."""

	def __init__(self, concurrency: int = 10, delay: float = 0.05) -> None:
		self._sem = asyncio.Semaphore(concurrency)
		self._delay = delay

	async def __aenter__(self):
		await self._sem.acquire()
		if self._delay:
			await asyncio.sleep(self._delay)
		return self

	async def __aexit__(self, *_exc):
		self._sem.release()