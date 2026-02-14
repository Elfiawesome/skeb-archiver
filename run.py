"""
Root-level runner – works from the terminal, Google Colab, or CI.

Usage
-----
Terminal            :  python run.py
Colab (cell)        :  await _main()
Module              :  python -m src.main
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.crawler import SkebCrawler
from src.logger import log
from src.site import generate_data

DATA_DIR = "skeb"
SITE_DIR = "docs"


async def _main() -> None:
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
	generate_data(data_dir=DATA_DIR, output_dir=SITE_DIR)
	log.info("Done.")


if __name__ == "__main__":
	asyncio.run(_main())