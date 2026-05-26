from dataclasses import dataclass

@dataclass
class Entry:
	screen_name: str = ""
	description_text: str = ""
	description_meta: dict[str]
	override_userdata: dict[str]

@dataclass
class Album:
	entires: list[Entry] = []