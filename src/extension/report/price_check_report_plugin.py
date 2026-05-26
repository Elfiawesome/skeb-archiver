from ...context import PipelineContext
from ...event.event import *
from ..extension_plugin import ExtensionPlugin
from ...registry import register_extension
from ...logger import log

@register_extension("price_check_report")
class PriceCheckReportPlugin(ExtensionPlugin):
	priority = 100

	def __init__(self):
		super().__init__()
	
	def on_event(self, context: PipelineContext, event: Event):
		
		if isinstance(event, ProfileFetchedEvent):
			event.data
