

from dataclasses import dataclass
from .data_store import DataStore
from .skeb_client import SkebClient

@dataclass
class PipelineContext:
	client: SkebClient
	store: DataStore
	cancel_pipeline_flag: bool = False