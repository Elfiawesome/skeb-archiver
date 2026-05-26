from dataclasses import dataclass, field

@dataclass
class Entry:
	screen_name: str = ""
	description_text: str = ""
	description_meta: dict[str] = field(default_factory=dict)
	override_userdata: dict[str] = field(default_factory=dict)

@dataclass
class Album:
	entires: list[Entry] = []