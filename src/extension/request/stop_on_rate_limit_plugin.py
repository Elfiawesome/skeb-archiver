from ...context import PipelineContext
from ...event.event import Event, ProfileFetchedEvent, ProfileTooManyRequestsFetchedEvent
from ...registry import register_extension
from ..extension_plugin import ExtensionPlugin

@register_extension("stop_on_rate_limit")
class StopOnRateLimit(ExtensionPlugin):
	def __init__(self, threshold: int = 10):
		super().__init__()
		self.threshold = threshold
		self.number_success_since_error: int = 0

	def on_event(self, context: PipelineContext, event: Event) -> None:
		if isinstance(event, ProfileFetchedEvent):
			self.number_success_since_error = 0
			self.check(context)

		elif isinstance(event, ProfileTooManyRequestsFetchedEvent):
			self.number_success_since_error += 1
			self.check(context)
	
	def check(self, context: PipelineContext) -> None:
		if self.number_success_since_error  > self.threshold:
			context.cancel_pipeline_flag = True
