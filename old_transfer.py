import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.crawler import SkebCrawler
from src.logger import log
from src.site import generate_data

DATA_DIR = "skeb"
SITE_DIR = "docs"

OLD_USERS = ""
MAX_REQ = 400
with open("old_users.txt", "r") as f:
	OLD_USERS = f.read()

async def _main() -> None:
	crawler = SkebCrawler(
		data_dir=DATA_DIR,
		concurrency=1,
		request_delay=0.05,
		page_size=90,
		pages_per_batch=10,
		max_items=-1,
		genre="art",
		retries=3,
	)
	async with crawler._client:
		names: list[list[str]] = []
		for line in OLD_USERS.split("\n"):
			if line == "": continue
			
			line_datas = line.split(",")
			if len(line_datas) == 0: continue
			if len(line_datas) == 1:
				if crawler._store.load(line_datas[0]):
					names.append([line_datas[0], "already saved"])
				else:
					names.append([line_datas[0]])
				continue

			if len(line_datas) == 2:
				names.append(line_datas)
				continue
		
		names.insert(1, ["uyo507"])
		for name in names:
			if len(name) == 1:
				try:
					data = await crawler._client.fetch_profile(name[0])
					crawler._persist(name[0], data)
				except Exception as e:
					name.append(str(e).replace("\n", "-").replace(",", "-"))

		with open("old_users.txt", "w") as f:
			for name in names:
				f.write(",".join(name) + "\n")
	
	generate_data(data_dir=DATA_DIR, output_dir=SITE_DIR)
	log.info("Done.")


if __name__ == "__main__":
	asyncio.run(_main())
