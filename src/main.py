"""
Package entry point.

	python -m src.main

The crawler writes raw per-user JSON to ``DATA_DIR`` (``skeb/``).
The discoverer scrapes similar_creators not yet stored.
The site generator reads from the *same* ``DATA_DIR`` and writes
derived lightweight files to ``SITE_DIR/api/`` (``docs/api/``).
"""

import asyncio

from .crawler import SkebCrawler
from .discover import Discoverer
from .logger import log
from .site import generate_data

DATA_DIR = "skeb"
SITE_DIR = "docs"


async def main() -> None:
	crawler = SkebCrawler(
		data_dir=DATA_DIR,
		concurrency=10,
		request_delay=0.05,
		page_size=90,
		pages_per_batch=10,
		max_items=-1,
		genre="art",
		retries=3,
	)
	await crawler.run()

	log.info("Discovering similar creators ...")
	discoverer = Discoverer(
		data_dir=DATA_DIR,
		concurrency=10,
		request_delay=0.05,
		retries=3,
	)
	await discoverer.run()

	log.info("Generating static-site data ...")
	generate_data(data_dir=DATA_DIR, output_dir=SITE_DIR)
	log.info("Done.")


if __name__ == "__main__":
	asyncio.run(main())