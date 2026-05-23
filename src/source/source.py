from typing import AsyncGenerator
from abc import ABC, abstractmethod
from ..context import PipelineContext

class Source(ABC):
	@abstractmethod
	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str,  None]:
		yield ""