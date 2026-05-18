from .extension.extension_plugin import ExtensionPlugin
from .event.event import Event, StartEvent, SourceRetrievedEvent, ProfilFetchedEvent, ProfileMissingEvent, EndEvent
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
		self.extensions.sort(key=lambda x: x.priority)

		self.raise_event(StartEvent())
		
		# Get who to scrape
		to_scrape: set[str] = set()
		to_scrape_count = 0
		for source in self.sources:
			async for user in source.get_sources(self.context):
				if user in to_scrape: continue
				
				evnt = SourceRetrievedEvent(user, to_scrape_count)
				
				self.raise_event(evnt)
				if evnt.allow: to_scrape.add(user)
				
				to_scrape_count += 1
		
		log.info(f"Ready to scrape {len(to_scrape)} items")

		# Run the scraping
		async for user in self.context.client.fetch_profiles(to_scrape):
			if user.get("failed", False):
				# Realize that if its just a 429 it reports as missing too which isn't intended
				self.raise_event(ProfileMissingEvent(screen_name=user.get("endpoint", "").replace("users/", "")))
			else:
				self.raise_event(ProfilFetchedEvent(user))
		

		self.raise_event(EndEvent())

	def raise_event(self, event: Event) -> None:
		for ext in self.extensions:
			ext.on_event(self.context, event)

