from dataclasses import dataclass, field, asdict

@dataclass
class Entry:
	screen_name: str = ""
	description_text: str = ""
	description_meta: dict[str] = field(default_factory=dict[str])
	override_userdata: dict[str] = field(default_factory=dict[str])

@dataclass
class Album:
	entires: list[Entry] = field(default_factory=list[Entry])

	def to_dict(self) -> dict[str]:
		return asdict(self)
	
	def is_empty(self) -> bool:
		return len(self.entires) == 0