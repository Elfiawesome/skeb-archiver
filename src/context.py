

from .data_store import DataStore
from .skeb_client import SkebClient

class PipelineContext:
	client: SkebClient
	store: DataStore