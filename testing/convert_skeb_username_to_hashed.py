from pathlib import Path
import hashlib
import re
BASE_DIR = Path().resolve() / "skeb"

def _safe(name: str) -> str:
	_SAFE_RE = re.compile(r"[^\w\-.]")
	safe_name = _SAFE_RE.sub("_", name)
	
	h = hashlib.md5(name.encode('utf-8')).hexdigest()[:6]
	return f"{safe_name}-{h}"

for file in BASE_DIR.glob("*.json"):
	original_name = file.with_suffix("").name
	new_name = _safe(original_name)
	file.rename(file.with_name(new_name).with_suffix(file.suffix))