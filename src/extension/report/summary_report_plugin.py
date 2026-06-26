from ...context import PipelineContext
from ...event.event import *
from ..extension_plugin import ExtensionPlugin
from ...registry import register_extension
from ...album import AlbumBuilder
from ...logger import log

@register_extension("summary_report")
class SummaryReportPlugin(ExtensionPlugin):
	priority = 100

	def __init__(self):
		super().__init__()
		self.fetched_names: list[str] = []
		self.sources_retreived: int = 0
		self.profile_missing: int = 0
		self.wrong_type_fetched: int = 0
		self.albums: dict[str, AlbumBuilder] = {
			"success": AlbumBuilder().set_name("success").set_label("Success").set_type("curated"),
			"rate_limited": AlbumBuilder().set_name("rate_limited").set_label("Rate Limited").set_type("curated"),
		}
		self.error_list: list[str] = []
		
	def on_event(self, context: PipelineContext, event: Event):
		
		if isinstance(event, SourceRetrievedEvent):
			self.sources_retreived += 1

		if isinstance(event, ProfileFetchedEvent):
			screen_name = event.data.get("screen_name", None)
			if screen_name:
				self.albums["success"].add_entry({"screen_name": screen_name})
		
		if isinstance(event, ProfileMissingEvent):
			self.profile_missing += 1
		
		if isinstance(event, ProfileTooManyRequestsFetchedEvent):
			self.albums["rate_limited"].add_entry({"screen_name": event.screen_name})
		
		if isinstance(event, ProfileErrorFetchEvent):
			self.error_list.append(event.endpoint)

		if isinstance(event, WrongTypeFetchEvent):
			self.wrong_type_fetched += 1
		

		if isinstance(event, EndEvent):
			log_text: str = " --- SUMMARY REPORT --- \n"
			log_text += "  %-20s : %d" % ("Sources Retreived", self.sources_retreived) + "\n"
			log_text += "  %-20s : %d" % ("Profiles Fetched", len(self.albums["success"].data)) + "\n"
			log_text += "  %-20s : %d" % ("Profile Missing", self.profile_missing) + "\n"
			log_text += "  %-20s : %d" % ("Profile Rate Limited", len(self.albums["rate_limited"].data)) + "\n"
			log_text += "  %-20s : %d" % ("Profile Error Others", len(self.error_list)) + "\n"
			log_text += "  %-20s : %d" % ("Wrong Type Fetched", self.wrong_type_fetched) + "\n"
			log.info(log_text)
			
			session_folder = context.store.open_session_date_folder()
			with (session_folder / "summary.txt").open("w", encoding="utf-8") as f: f.write(log_text)
			


			# import json
			for album_name in self.albums:
				a = self.albums[album_name]
				if a.is_empty(): continue
				a.set_date(context.store.timestamp_now())
				a.build()

				context.store.store_album(a, session_folder)