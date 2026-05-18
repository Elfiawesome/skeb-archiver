from ..context import PipelineContext
from ..event.event import Event
from abc import ABC, abstractmethod

class ExtensionPlugin(ABC):
	@abstractmethod
	def on_event(self, context: PipelineContext, event: Event) -> None:
		pass