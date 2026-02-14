"""Generate docs/data.json from skeb/*.json user files."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .logger import log
from .store import DataStore


def generate_data(
	data_dir: str = "skeb",
	output_dir: str = "docs",
) -> None:
	"""Read every user file and write a single ``data.json`` for the static site."""
	store = DataStore(data_dir)
	all_users = store.load_all()

	out = Path(output_dir)
	out.mkdir(parents=True, exist_ok=True)

	users: List[Dict[str, Any]] = []
	for u in all_users:
		users.append(
			{
				"screen_name": u.get("screen_name", ""),
				"first_seen": u.get("first_seen", ""),
				"last_updated": u.get("last_updated", ""),
				"works_count": len(u.get("works", [])),
				"price_history": u.get("price_history", {}),
				"works": [
					{
						"path": w.get("path", ""),
						"scraped_at": w.get("scraped_at", ""),
					}
					for w in u.get("works", [])
				],
			}
		)

	payload = {
		"generated_at": datetime.now(timezone.utc).isoformat(),
		"user_count": len(users),
		"users": users,
	}

	dest = out / "data.json"
	with dest.open("w", encoding="utf-8") as fh:
		json.dump(payload, fh, ensure_ascii=False)

	log.info("Static site data: %s  (%d users)", dest, len(users))