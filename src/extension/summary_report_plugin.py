from ..context import PipelineContext
from ..event.event import Event, ProfilFetchedEvent, SourceRetrievedEvent, ProfileMissingEvent, ProfileTooManyRequestsFetchedEvent, EndEvent
from .extension_plugin import ExtensionPlugin
from ..logger import log

class SummaryReportPlugin(ExtensionPlugin):
	priority = 100

	def __init__(self):
		super().__init__()
		self.fetched_names: list[str] = []
		self.profiles_fetched: int = 0
		self.sources_retreived: int = 0
		self.profile_missing: int = 0
		self.profile_rate_limited: int = 0
	
	def on_event(self, context: PipelineContext, event: Event):
		
		if isinstance(event, SourceRetrievedEvent):
			self.sources_retreived += 1

		if isinstance(event, ProfilFetchedEvent):
			self.profiles_fetched += 1
		
		if isinstance(event, ProfileMissingEvent):
			self.profile_missing += 1
		
		if isinstance(event, ProfileTooManyRequestsFetchedEvent):
			self.profile_rate_limited += 1

		if isinstance(event, EndEvent):
			log_text: str = " --- SUMMARY REPORT --- "
			log_text += "  %-20s : %d", "Sources Retreived", self.sources_retreived
			log_text += "  %-20s : %d", "Profiles Fetched", self.profiles_fetched
			log_text += "  %-20s : %d", "Profile Missing", self.profile_missing
			log_text += "  %-20s : %d", "Profile Rate Limited", self.profile_rate_limited
			log.info(log_text)

			with (context.store._root.parent / "output.txt").open("w", encoding="utf-8") as f:
				f.write(log_text)