from pathlib import Path
from src.store import DataStore

BASE_DIR = Path().resolve() / "skeb"

for file in BASE_DIR.glob("*.json"):
	original_name = file.with_suffix("").name
	new_name = DataStore.username_safe(original_name)
	file.rename(file.with_name(new_name).with_suffix(file.suffix))