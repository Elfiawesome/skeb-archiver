"""
Root-level runner.

Works three ways:
	1.  python run.py
	2.  In Google Colab:  exec(open("run.py").read())   OR   await _main()
	3.  python -m src.main   (uses the package entry point instead)
"""

import asyncio
import sys
import os

# Ensure the project root is on sys.path so ``src`` is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.crawler import SkebCrawler
from src.site import generate_data
from src.logger import log


async def _main() -> None:
	crawler = SkebCrawler(
		data_dir="skeb",
		concurrency=10,
		request_delay=0.05,
		page_size=90,
		pages_per_batch=10,
		max_items=-1,        # set to e.g. 900 for a quick test
		genre="art",
		retries=3,
	)
	await crawler.run()
	generate_data(data_dir="skeb", output_dir="docs")
	log.info("All done.")


if __name__ == "__main__":
	asyncio.run(_main())