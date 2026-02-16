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
	rescraper = Rescraper(
		data_dir=DATA_DIR,
		concurrency=10,
		request_delay=0.05,
		retries=3,
	)
	# Additional filter to only updaate those who are more than 5 day old
	def f(data: dict) -> bool:
		import datetime
		last_updated_string =  data.get("last_updated")
		last_update = datetime.datetime.fromisoformat(last_updated_string)
		today = datetime.datetime.now()
		if (last_update - today) > datetime.timedelta(days=5):
			return True
		return False
	await rescraper.run(f)

	log.info("Regenerating static-site data ...")
	generate_data(data_dir=DATA_DIR, output_dir=SITE_DIR)
	log.info("Rescrape complete.")


if __name__ == "__main__":
	asyncio.run(_main())