"""
Re-scrape all existing users and regenerate the static site.

	python run_rescrape.py

In Colab:
	await _main()
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.rescrape import Rescraper
from src.site import generate_data
from src.logger import log

DATA_DIR = "skeb"
SITE_DIR = "docs"


async def _main() -> None:
	# rescraper = Rescraper(
	# 	data_dir=DATA_DIR,
	# 	concurrency=10,
	# 	request_delay=0.05,
	# 	retries=3,
	# )
	# Additional filter to only updaate those who are more than 5 day old
	import datetime
	def f(data: dict) -> bool:
		last_updated_string = data.get("last_updated")
		if not last_updated_string:
			return True
		last_update = datetime.datetime.fromisoformat(last_updated_string)
		today = datetime.datetime.now(tz=datetime.timezone.utc)
		
		print(last_update, " - ",today)
		
		if (today - last_update) > datetime.timedelta(days=5):
			return True
		return False
	from src.store import DataStore
	ds = DataStore(DATA_DIR)
	print(ds.list_screen_names(f))

	# await rescraper.run(f)

	# log.info("Regenerating static-site data ...")
	# generate_data(data_dir=DATA_DIR, output_dir=SITE_DIR)
	# log.info("Rescrape complete.")


if __name__ == "__main__":
	asyncio.run(_main())