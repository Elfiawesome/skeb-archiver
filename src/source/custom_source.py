from typing import AsyncGenerator
from .source import Source
from ..registry import register_source
from ..context import PipelineContext

@register_source("custom")
class CustomSource(Source):
	def __init__(self, names: tuple[str] = ()):
		super().__init__()
		self.screen_names = names

	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		for n in self.screen_names:
			yield n