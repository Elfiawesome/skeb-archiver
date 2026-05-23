from typing import AsyncGenerator
from .source import Source
from ..context import PipelineContext
import datetime

class RescrapeSource(Source):
	
	def __init__(self, stale_days):
		super().__init__()
		self.stale_days = stale_days
	
	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		for user in context.store.load_all():
			if "screen_name" in user:
				if self.stale_filtered(user):
					yield user["screen_name"]


	def stale_filtered(self, user: dict[str]) -> bool:
		if self.stale_days <= 0: return True
		ts: float = user.get("last_updated")
		if ts:
			last = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
			now = datetime.datetime.now(tz=datetime.timezone.utc)
			if (now - last) > datetime.timedelta(days=self.stale_days):
				return False
		return False
