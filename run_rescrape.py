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
		concurrency=1,
		request_delay=0.1,
		retries=3,
	)
	await rescraper.run()

	log.info("Regenerating static-site data ...")
	generate_data(data_dir=DATA_DIR, output_dir=SITE_DIR)
	log.info("Rescrape complete.")


if __name__ == "__main__":
	asyncio.run(_main())