from ..context import PipelineContext
from ..event.event import Event, SourceRetrievedEvent
from .extension_plugin import ExtensionPlugin

class SourcingLimitPlugin(ExtensionPlugin):
	def __init__(self, limit: int = 10):
		super().__init__()
		self.limit: int = limit
	
	def on_event(self, context: PipelineContext, event: Event):
		if isinstance(event, SourceRetrievedEvent):
			if event.current_count > self.limit:
				event.allow = False