from typing import AsyncGenerator
from .source import Source
from ..context import PipelineContext

class DebugSource(Source):
	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		yield "INSERT NAME HERE"