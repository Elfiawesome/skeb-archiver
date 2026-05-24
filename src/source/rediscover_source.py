from typing import AsyncGenerator
from .source import Source
from ..registry import register_source
from ..context import PipelineContext

@register_source("rediscover")
class RediscoverSource(Source):
	
	def __init__(self):
		super().__init__()
	
	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		existing: set[str] = set()
		candidates: set[str] = set()

		for user in context.store.load_all():
			profile: dict[str] = user.get("profile", {})
			similar_creators: list[dict[str]] = profile.get("similar_creators", [])
			
			user_sn: str = user.get("screen_name", None)
			if user_sn:
				existing.add(user_sn)

			for sc in similar_creators:
				sc_sn: str = sc.get("screen_name", None)
				if sc_sn:
					candidates.add(sc_sn)
			
			new_names = candidates - existing

			for n in new_names:
				yield n
					

