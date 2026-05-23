from ..context import PipelineContext
from ..event.event import Event
from abc import ABC, abstractmethod

class ExtensionPlugin(ABC):
	priority: int = 0

	@abstractmethod
	def on_event(self, context: PipelineContext, event: Event) -> None:
		pass