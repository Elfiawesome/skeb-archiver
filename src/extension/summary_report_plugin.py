from ..context import PipelineContext
from ..event.event import *
from .extension_plugin import ExtensionPlugin
from ..registry import register_extension
from ..logger import log

@register_extension("summary_report")
class SummaryReportPlugin(ExtensionPlugin):
	priority = 100

	def __init__(self):
		super().__init__()
		self.fetched_names: list[str] = []
		self.profiles_fetched: int = 0
		self.sources_retreived: int = 0
		self.profile_missing: int = 0
		self.profile_rate_limited: int = 0
		self.profile_error_others: int = 0
	
	def on_event(self, context: PipelineContext, event: Event):
		
		if isinstance(event, SourceRetrievedEvent):
			self.sources_retreived += 1

		if isinstance(event, ProfileFetchedEvent):
			self.profiles_fetched += 1
		
		if isinstance(event, ProfileMissingEvent):
			self.profile_missing += 1
		
		if isinstance(event, ProfileTooManyRequestsFetchedEvent):
			self.profile_rate_limited += 1
		
		if isinstance(event, ProfileErrorFetchEvent):
			self.profile_error_others += 1


		if isinstance(event, EndEvent):
			log_text: str = " --- SUMMARY REPORT --- \n"
			log_text += "  %-20s : %d" % ("Sources Retreived", self.sources_retreived) + "\n"
			log_text += "  %-20s : %d" % ("Profiles Fetched", self.profiles_fetched) + "\n"
			log_text += "  %-20s : %d" % ("Profile Missing", self.profile_missing) + "\n"
			log_text += "  %-20s : %d" % ("Profile Rate Limited", self.profile_rate_limited) + "\n"
			log_text += "  %-20s : %d" % ("Profile Error Others", self.profile_error_others) + "\n"
			log.info(log_text)
			
			session_folder = context.store.open_session_date_folder()
			with (session_folder / "summary.txt").open("w", encoding="utf-8") as f: f.write(log_text)
			
			# with (session_folder / "summary.txt").open("w", encoding="utf-8") as f:
			# 	f.write(log_text)