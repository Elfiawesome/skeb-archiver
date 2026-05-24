from datetime import datetime, timezone, timedelta
from ..context import PipelineContext
from ..event.event import Event, SourceRetrievedEvent
from ..registry import register_extension
from .extension_plugin import ExtensionPlugin

@register_extension("stale_filter")
class SourcingStateFilterPlugin(ExtensionPlugin):
	def __init__(self, stale_days: int = 5):
		super().__init__()
		self.stale_days = stale_days

	def on_event(self, context: PipelineContext, event: Event) -> None:
		if not isinstance(event, SourceRetrievedEvent):
			return

		if not event.allow: # Keep it blocked
			return

		user_data = context.store.load(event.user)

		# No data -> new user -> treat as stale -> allow
		if not user_data:
			return

		last_updated = user_data.get("last_updated")
		if not last_updated:
			# No timestamp, treat as stale -> allow
			return

		# Compare with threshold
		last = datetime.fromtimestamp(last_updated, tz=timezone.utc)
		now = datetime.now(tz=timezone.utc)
		age = now - last
		if age <= timedelta(days=self.stale_days):
			# Still fresh -> block
			event.allow = False