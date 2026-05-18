from .extension.extension_plugin import ExtensionPlugin
from .event.event import Event, StartEvent, SourceRetreivedEvent, ProfilFetchedEvent
from .source.source import Source
from .data_store import DataStore
from .skeb_client import SkebClient
from .context import PipelineContext
from .logger import log

class Pipeline:
	sources: list[Source] = []
	extensions: list[ExtensionPlugin] = []
	
	def __init__(self, store: DataStore, client: SkebClient):
		self.context: PipelineContext = PipelineContext()
		self.context.store = store
		self.context.client = client

	async def run(self) -> None:
		self.raise_event(StartEvent())
		
		# Get who to scrape
		to_scrape: list[str] = []
		for source in self.sources:
			async for user in source.get_sources(self.context):
				self.raise_event(SourceRetreivedEvent(user))
				to_scrape.append(user)
		log.info(f"Ready to scrape {len(to_scrape)} items")

		# Run the scraping
		async for user in self.context.client.fetch_profiles(to_scrape):
			self.raise_event(ProfilFetchedEvent(user))

	def raise_event(self, event: Event) -> None:
		for ext in self.extensions:
			ext.on_event(self.context, event)

