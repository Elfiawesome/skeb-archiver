from abc import ABC
from dataclasses import dataclass

class Event(ABC):
	pass

@dataclass
class StartEvent(Event):
	pass


@dataclass
class SourceRetrievedEvent(Event):
	user: str
	current_count: int = 0
	allow: bool = True

@dataclass
class ProfileFetchedEvent(Event):
	data: dict[str]

@dataclass
class ProfileMissingEvent(Event):
	screen_name: str

@dataclass
class ProfileTooManyRequestsFetchedEvent(Event):
	screen_name: str

@dataclass
class ProfileErrorFetchEvent(Event):
	error: str
	status_code: int
	endpoint: str

@dataclass
class WrongTypeFetchEvent(Event):
	expected_type: type
	received_type: type
	received_data: dict | list | None


@dataclass
class EndEvent(Event):
	pass