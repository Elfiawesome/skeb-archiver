from .extension.extension_plugin import ExtensionPlugin
from .event.event import Event, StartEvent, SourceRetrievedEvent, ProfilFetchedEvent, ProfileMissingEvent, ProfileTooManyRequestsFetchedEvent, EndEvent
from .source.source import Source
from .data_store import DataStore
from .skeb_client import SkebClient
from .context import PipelineContext
from .logger import log

class Pipeline:
	
	def __init__(self, store: DataStore, client: SkebClient):
		self.sources: list[Source] = []
		self.extensions: list[ExtensionPlugin] = []
	
		self.context: PipelineContext = PipelineContext()
		self.context.store = store
		self.context.client = client
	
	async def run(self) -> None:
		# 0. Setup process
		self._setup()

		# 1. Get sources from all
		sources = await self.get_sources()
		log.info(f"Ready to scrape {len(sources)} items")

		# 2. Fetch all profiles
		await self._fetch_profiles_from_sources(sources)

		# 4. End!
		self.raise_event(EndEvent())

	def _setup(self) -> None:
		self.extensions.sort(key=lambda x: x.priority)
		self.raise_event(StartEvent())

	async def get_sources(self) -> set[str]:
		sources: set[str] = set()
		sources_count = 0
		for source in self.sources:
			async for user in source.get_sources(self.context):
				if user in sources: continue
				
				evnt = SourceRetrievedEvent(user, sources_count)
				
				self.raise_event(evnt)
				if evnt.allow: sources.add(user)
				
				sources_count += 1
		
		return sources

	async def _fetch_profiles_from_sources(self, sources: set[str]) -> None:
		async for user in self.context.client.fetch_profiles(sources):
			if user.get("failed", False):
				sn: str = user.get("endpoint", "").replace("users/", "")
				sc: int | None = user.get("status_code")
				if sc == 429: self.raise_event(ProfileTooManyRequestsFetchedEvent(screen_name=sn))
				elif sc == 404: self.raise_event(ProfileMissingEvent(screen_name=sn))
			else:
				self.raise_event(ProfilFetchedEvent(user))

	def raise_event(self, event: Event) -> None:
		for ext in self.extensions:
			ext.on_event(self.context, event)

