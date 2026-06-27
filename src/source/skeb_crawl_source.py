from typing import AsyncGenerator
from ..registry import register_source
from .source import Source
from ..context import PipelineContext
import re

@register_source("skeb_crawl")
class SkebCrawlSource(Source):
	_WORK_RE = re.compile(r"/@([^/]+)/works/(\d+)")
	
	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		async for item in context.client.fetch_paginate(type_="works", genre="art"):
			if "path" in item:
				m = self._WORK_RE.search(item.get("path", ""))
				if m:
					yield m.group(1)
			
		async for item in context.client.fetch_paginate(type_="users", genre="art"):
			if "screen_name" in item:
				yield item["screen_name"]

