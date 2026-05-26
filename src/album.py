from dataclasses import dataclass

@dataclass
class Entry:
	screen_name: str = ""
	description_text: str = ""
	description_meta: dict[str] | None = None
	override_userdata: dict[str] | None = None

@dataclass
class Album:
	entires: list[Entry] = []