from typing import AsyncGenerator
from .source import Source
from ..context import PipelineContext

class RediscoverSource(Source):
	
	def __init__(self):
		super().__init__()
	
	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		for user in context.store.load_all():
			profile: dict[str] = user.get("profile", {})
			similar_creators: list[dict[str]] = profile.get("similar_creators", [])
			for sc in similar_creators:
				sn: str = sc.get("screen_name", None)
				if sn:
					yield sn