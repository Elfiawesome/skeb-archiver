from ..skeb_client import SkebClient
from abc import ABC
from dataclasses import dataclass

class Event(ABC):
	pass

@dataclass
class StartEvent(Event):
	pass


@dataclass
class SourceRetreivedEvent(Event):
	user: str


@dataclass
class ProfilFetchedEvent(Event):
	data: dict[str]