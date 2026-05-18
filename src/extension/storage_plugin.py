from ..context import PipelineContext
from ..event.event import Event, ProfilFetchedEvent
from .extension_plugin import ExtensionPlugin

class StoragePlugin(ExtensionPlugin):
	def on_event(self, context: PipelineContext, event: Event):
		if isinstance(event, ProfilFetchedEvent):
			if "screen_name" in event.data:
				context.store.update_save(event.data["screen_name"], event.data)
			else:
				pass