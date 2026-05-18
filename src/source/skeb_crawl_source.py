from typing import AsyncGenerator
from .source import Source
from ..context import PipelineContext

class SkebCrawlSource(Source):
	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		async for item in context.client.fetch_paginate(type="works", genre="art"):
			if "screen_name" in item:
				yield item["screen_name"]