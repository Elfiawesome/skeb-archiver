from ..context import PipelineContext
from ..event.event import Event, ProfilFetchedEvent, SourceRetreivedEvent, ProfileMissingEvent, EndEvent
from .extension_plugin import ExtensionPlugin
from ..logger import log

class SummaryReportPlugin(ExtensionPlugin):
	priority = 100
	profiles_fetched: int = 0
	sources_retreived: int = 0
	profile_missing: int = 0
	
	def on_event(self, context: PipelineContext, event: Event):
		
		if isinstance(event, SourceRetreivedEvent):
			self.sources_retreived += 1

		if isinstance(event, ProfilFetchedEvent):
			self.profiles_fetched += 1
		
		if isinstance(event, ProfileMissingEvent):
			self.profile_missing += 1

		if isinstance(event, EndEvent):
			log.info(" --- SUMMARY REPORT --- ")
			log.info("  %-20s : %d", "Sources Retreived", self.sources_retreived)
			log.info("  %-20s : %d", "Profiles Fetched", self.profiles_fetched)
			log.info("  %-20s : %d", "Profile Missing", self.profile_missing)