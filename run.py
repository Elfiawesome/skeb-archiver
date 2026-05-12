"""
Unified runner for Skeb Archiver.

Usage
-----
Terminal:
	python run.py				   Run all steps (crawl + discover + rescrape)
	python run.py crawl			 Discover users from global listings
	python run.py rescrape		  Refresh existing user profiles
	python run.py discover		  Scrape similar_creators not yet stored
	python run.py all			   Alias for running all steps

Options:
	--stale-days N	 Only rescrape users not updated in N days (default: 5)
	--no-site		  Skip static-site regeneration
	--concurrency N	Max parallel requests (default: 10)
	--delay SECS	   Per-request delay in seconds (default: 0.05)
	--retries N		Max retries per request (default: 3)
	--max-users N		Max users (default: -1)

Colab:
	await _main()				   Run all steps with defaults
	await _main("crawl")			Run just crawl
	await _main("rescrape")		 Run just rescrape
	await _main("discover")		 Run just discover
	await _main("rescrape", stale_days=3)
"""

import argparse
import asyncio
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.crawler import SkebCrawler
from src.discover import Discoverer
from src.rescrape import Rescraper
from src.site import generate_data
from src.logger import log

DATA_DIR = "docs/skeb"
SITE_DIR = "docs"

_DEFAULTS = dict(
	concurrency=10,
	delay=0.05,
	retries=3,
	stale_days=5,
	no_site=False,
	max_users=-1,
)

_ALL_MODES = ["crawl", "discover", "rescrape"]


# ── per-mode runners ────────────────────────────────────────────

def _stale_filter(days: int):
	"""Return a filter that selects users not updated in *days* days."""
	def _filter(data: dict) -> bool:
		ts = data.get("last_updated")
		if not ts:
			return True
		last = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
		now = datetime.datetime.now(tz=datetime.timezone.utc)
		return (now - last) > datetime.timedelta(days=days)
	return _filter


async def _run_crawl(concurrency, delay, retries, **_kw) -> None:
	crawler = SkebCrawler(
		data_dir=DATA_DIR,
		concurrency=concurrency,
		request_delay=delay,
		page_size=90,
		pages_per_batch=10,
		max_items=-1,
		genre="art",
		retries=retries,
	)
	await crawler.run()


async def _run_discover(concurrency, delay, retries, **_kw) -> None:
	discoverer = Discoverer(
		data_dir=DATA_DIR,
		concurrency=concurrency,
		request_delay=delay,
		retries=retries,
		max_users=_kw["max_users"],
	)
	await discoverer.run()


async def _run_rescrape(concurrency, delay, retries, stale_days, **_kw) -> None:
	rescraper = Rescraper(
		data_dir=DATA_DIR,
		concurrency=concurrency,
		request_delay=delay,
		retries=retries,
	)
	await rescraper.run(_stale_filter(stale_days))


_RUNNERS = {
	"crawl": _run_crawl,
	"discover": _run_discover,
	"rescrape": _run_rescrape,
}


# ── main entry point ────────────────────────────────────────────

async def _main(mode="all", **overrides) -> None:
	"""
	Entry point — callable from CLI or Colab.

	Parameters
	----------
	mode : str
		One of ``"crawl"``, ``"rescrape"``, ``"discover"``, or ``"all"``.
	**overrides :
		Any of concurrency, delay, retries, stale_days, no_site.
	"""
	opts = {**_DEFAULTS, **overrides}
	modes = _ALL_MODES if mode == "all" else [mode]

	for m in modes:
		await _RUNNERS[m](**opts)

	if not opts["no_site"]:
		log.info("Generating static-site data ...")
		generate_data(data_dir=DATA_DIR, output_dir=SITE_DIR)

	log.info("Done.")


# ── CLI ──────────────────────────────────────────────────────────

def _parse_args() -> dict:
	p = argparse.ArgumentParser(description="Skeb Archiver runner")
	p.add_argument(
		"mode", nargs="?", default="all",
		choices=["crawl", "rescrape", "discover", "all"],
		help="Operation mode (default: all)",
	)
	p.add_argument("--stale-days", type=int, default=_DEFAULTS["stale_days"],
				   help="Rescrape users not updated in N days (default: 5)")
	p.add_argument("--no-site", action="store_true",
				   help="Skip static-site generation")
	p.add_argument("--concurrency", type=int, default=_DEFAULTS["concurrency"])
	p.add_argument("--delay", type=float, default=_DEFAULTS["delay"])
	p.add_argument("--retries", type=int, default=_DEFAULTS["retries"])
	p.add_argument("--max-users", type=int, default=_DEFAULTS["max_users"])
	a = p.parse_args()
	return dict(
		mode=a.mode,
		stale_days=a.stale_days,
		no_site=a.no_site,
		concurrency=a.concurrency,
		delay=a.delay,
		retries=a.retries,
		max_users=a.max_users,
	)


if __name__ == "__main__":
	asyncio.run(_main(**_parse_args()))