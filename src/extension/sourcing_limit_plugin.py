from ..context import PipelineContext
from ..event.event import Event, SourceRetreivedEvent
from .extension_plugin import ExtensionPlugin

class SourcingLimitPlugin(ExtensionPlugin):
	def on_event(self, context: PipelineContext, event: Event):
		if isinstance(event, SourceRetreivedEvent):
			if event.current_count > 10:
				event.allow = False