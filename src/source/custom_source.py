from typing import AsyncGenerator
from .source import Source
from ..context import PipelineContext

class CustomSource(Source):
	def __init__(self, names: tuple[str] = ()):
		super().__init__()
		self.screen_names = names

	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		for n in self.screen_names:
			yield n