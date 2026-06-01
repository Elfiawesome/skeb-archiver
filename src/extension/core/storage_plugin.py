
from ...context import PipelineContext
from ...event.event import *
from ...registry import register_extension
from ..extension_plugin import ExtensionPlugin

@register_extension("storage")
class StoragePlugin(ExtensionPlugin):
	priority = 120
	
	def on_event(self, context: PipelineContext, event: Event):
		if isinstance(event, ProfileFetchedEvent):
			if "screen_name" in event.data:
				udpated_data = context.store.update_save(event.data["screen_name"], event.data)
				
				# Update missing data if it was found again
				custom_data: dict[str] =  udpated_data.get("custom")
				if "missing" in custom_data:
					if custom_data["missing"] == True:
						context.store.update_custom_data(event.data["screen_name"], "missing", None)
		
		if isinstance(event, ProfileMissingEvent):
			if event.screen_name:
				context.store.update_custom_data(event.screen_name, "missing", True)
		
		if isinstance(event, EndEvent):
			context.store.create_api_data()