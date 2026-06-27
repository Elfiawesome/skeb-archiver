"""
Skeb Archiver Pipeline Runner

Usage:
# Preset modes
python run.py --preset crawl
python run.py --preset rescrape
python run.py --preset rediscover
python run.py --preset custom --names user1 user2

# Load from a JSON config file
python run.py --config my_config.json

# Build your own pipeline with CLI arguments
python run.py --source skeb_crawl \
				--source rescrape:stale_days=3 \
				--extension storage \
				--extension summary_report \
				--extension sourcing_limit:limit=50

For more details, use: python run.py --help
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from src.source.skeb_crawl_source import SkebCrawlSource
from src.source.rescrape_source import RescrapeSource
from src.source.rediscover_source import RediscoverSource
from src.source.custom_source import CustomSource
from src.extension.request.stop_on_rate_limit_plugin import StopOnRateLimit
from src.extension.source.source_limit_plugin import SourceLimitPlugin
from src.extension.source.source_state_filter_plugin import SourceStateFilterPlugin
from src.extension.core.storage_plugin import StoragePlugin
from src.extension.report.summary_report_plugin import SummaryReportPlugin
from src.extension.report.price_drop_album_plugin import PriceDropAlbumPlugin

from src.pipeline import Pipeline
from src.data_store import DataStore
from src.skeb_client import SkebClient
from src.registry import create_source, create_extension

# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------
PRESETS: dict[str, dict[str, list[tuple[str, dict]]]] = {
	"crawl": {
		"sources": [("skeb_crawl", {})],
		"extensions": [("storage", {}), ("summary_report", {})],
	},
	"rescrape": {
		"sources": [("rescrape", {"stale_days": 5})],
		"extensions": [("storage", {}), ("summary_report", {})],
	},
	"rediscover": {
		"sources": [("rediscover", {})],
		"extensions": [("storage", {}), ("summary_report", {})],
	},
	"build_site": {
		"sources": [],
		"extensions": [("storage", {}), ("summary_report", {})],
	},
	# testing only
	"debug-me": {
		"sources": [("custom", {"names": [
			"EV_shiro",
			"grrrrrwf",
			"ImasimeNai",
			"masso_nullbuilt",
			"miripesosan",
			"nanzuyo",
			"nectar_x_x",
			"nomeoir",
			"Phcatss",
			"sg_makuri",
			"skeb_k4",
			"slumpa1008",
			"susu__hu0o",
			"touhinyut",
			"tunral",
			"uenomigi",
			"usahana101",
			"ve_0ekaki",
		]})],
		"extensions": [("storage", {}), ("summary_report", {}), ("source_limit", {"limit": 5})],
	},
	"custom": {
		"sources": [("custom", {"names": []})],  # names will be set via --names
		"extensions": [("storage", {}), ("summary_report", {})],
	},
}

# ---------------------------------------------------------------------------
# Helpers for parsing source/extension spec strings
# ---------------------------------------------------------------------------
def parse_spec(spec: str) -> tuple[str, dict[str, Any]]:
	"""
	Parse a spec string like 'rescrape:stale_days=5' or 'custom:names=a,b'.
	Returns (name, kwargs_dict).
	"""
	if ":" in spec:
		name, params_str = spec.split(":", 1)
	else:
		name = spec
		params_str = ""

	kwargs: dict[str, Any] = {}
	if params_str:
		for part in params_str.split(","):
			if "=" in part:
				k, v = part.split("=", 1)
				k = k.strip()
				v = v.strip()
				# Handle list-type parameters (currently only "names")
				if k in ("names",):  # extend this set if needed
					kwargs[k] = [item.strip() for item in v.split(",") if item.strip()]
				else:
					# Try int, then float, else string
					try:
						kwargs[k] = int(v)
					except ValueError:
						try:
							kwargs[k] = float(v)
						except ValueError:
							kwargs[k] = v
			# if no '=', ignore (could be used for flags later)
	return name, kwargs


def build_sources_extensions(
	sources_specs: list[tuple[str, dict]],
	extensions_specs: list[tuple[str, dict]],
) -> tuple[list, list]:
	"""Instantiate source and extension objects from spec tuples."""
	sources = [create_source(name, **kwargs) for name, kwargs in sources_specs]
	extensions = [create_extension(name, **kwargs) for name, kwargs in extensions_specs]
	return sources, extensions


# ---------------------------------------------------------------------------
# Config file loading
# ---------------------------------------------------------------------------
def load_config(filepath: str) -> dict[str, Any]:
	"""Load and validate a JSON configuration file."""
	with open(filepath, "r", encoding="utf-8") as f:
		config = json.load(f)

	# Validate structure – must have "sources" and "extensions" lists
	if not isinstance(config.get("sources"), list):
		raise ValueError("Config file must contain a 'sources' list")
	if not isinstance(config.get("extensions"), list):
		raise ValueError("Config file must contain an 'extensions' list")

	return config


def config_to_specs(config: dict) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]], str | None, str | None, dict[str, Any]]:
	"""Extract source/extension specs, directory settings, and client params from config dict."""
	source_specs = []
	for src in config["sources"]:
		name = src["name"]
		params = src.get("params", {})
		source_specs.append((name, params))

	ext_specs = []
	for ext in config["extensions"]:
		name = ext["name"]
		params = ext.get("params", {})
		ext_specs.append((name, params))

	docs_dir = config.get("docs_dir", "docs")
	persistance_dir = config.get("persistance_dir", None)
	client_params = config.get("client", {})
	return source_specs, ext_specs, docs_dir, persistance_dir, client_params


# ---------------------------------------------------------------------------
# Main pipeline execution
# ---------------------------------------------------------------------------
async def run_pipeline(
	sources_specs: list[tuple[str, dict]],
	extensions_specs: list[tuple[str, dict]],
	docs_dir: str = "docs",
	persistance_dir: str | None = None,
	max_concurrency: int = 10,
	max_retries: int = 3,
	timeout_sec: int = 30,
	rate_per_sec: float = 3.0,
	paginate_batch_size: int = 10,
	impersonate: str = "chrome120",
) -> None:
	"""Create and run the pipeline with given specifications."""
	store = DataStore(docs_dir=docs_dir, persistance_dir=persistance_dir)
	sources, extensions = build_sources_extensions(sources_specs, extensions_specs)

	async with SkebClient(
		max_concurrency=max_concurrency,
		max_retries=max_retries,
		timeout_sec=timeout_sec,
		paginate_batch_size=paginate_batch_size,
		rate_per_sec=rate_per_sec,
		impersonate=impersonate,
	) as client:
		pipeline = Pipeline(store, client)

		for src in sources:
			pipeline.add_source(src)
		for ext in extensions:
			pipeline.add_extension(ext)

		await pipeline.run()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def main() -> None:
	parser = argparse.ArgumentParser(
		description="Skeb Archiver Pipeline Runner",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog="""
Examples:
python run.py --preset crawl
python run.py --preset custom --names alice bob
python run.py --config myconfig.json
python run.py --source skeb_crawl --extension storage --extension summary_report
		""",
	)

	# Mutually exclusive top‑level mode selection
	mode_group = parser.add_mutually_exclusive_group()
	mode_group.add_argument(
		"--config",
		type=str,
		help="Path to a JSON configuration file (ignores --preset, --source, --extension)",
	)
	mode_group.add_argument(
		"--preset",
		choices=list(PRESETS.keys()),
		help="Use a predefined pipeline configuration",
	)

	# Manual / override arguments (allowed when --preset or no mode is given)
	parser.add_argument(
		"--source",
		action="append",
		dest="sources",
		help='Add a source (format: "name[:key=val,...]"). Repeatable.',
	)
	parser.add_argument(
		"--extension",
		action="append",
		dest="extensions",
		help='Add an extension (format: "name[:key=val,...]"). Repeatable.',
	)
	parser.add_argument(
		"--docs-dir",
		default="docs",
		help="Directory where skeb JSON files are stored (default: docs)",
	)
	parser.add_argument(
		"--persistance-dir",
		default="persistance",
		help="Directory for session logs / summaries (default: same as docs-dir)",
	)
	parser.add_argument(
		"--names",
		nargs="*",
		help="List of screen names for the 'custom' source (used with --preset custom or manual --source custom)",
	)
	parser.add_argument(
		"--max-concurrency",
		type=int,
		default=10,
		help="Maximum concurrent requests (default: 10)",
	)
	parser.add_argument(
		"--max-retries",
		type=int,
		default=3,
		help="Maximum retry attempts per request (default: 3)",
	)
	parser.add_argument(
		"--timeout",
		type=int,
		default=30,
		help="HTTP request timeout in seconds (default: 30)",
	)
	parser.add_argument(
		"--rate",
		type=float,
		default=3.0,
		help="Max requests per second (default: 3.0)",
	)
	parser.add_argument(
		"--impersonate",
		type=str,
		default="chrome120",
		help="Browser TLS fingerprint to impersonate: chrome110, chrome120, firefox110, safari17_0, edge101, etc. (default: chrome120)",
	)
	parser.add_argument(
		"--paginate-batch-size",
		type=int,
		default=10,
		help="Number of pagination pages per batch (default: 10)",
	)

	args = parser.parse_args()

	# Determine source and extension specifications
	sources_specs: list[tuple[str, dict]] = []
	extensions_specs: list[tuple[str, dict]] = []
	docs_dir = args.docs_dir
	persistance_dir = args.persistance_dir
	config_client_params: dict[str, Any] = {}

	if args.config:
		# Config mode – ignore preset and manual args
		if args.preset or args.sources or args.extensions or args.names:
			parser.error(
				"--config cannot be combined with --preset, --source, --extension, or --names"
			)
		try:
			config = load_config(args.config)
			sources_specs, extensions_specs, docs_dir, persistance_dir, config_client_params = config_to_specs(config)
		except Exception as e:
			print(f"Error loading config file: {e}", file=sys.stderr)
			sys.exit(1)

	elif args.preset:
		# Preset mode – start from preset, then add any extra --source/--extension
		preset = PRESETS[args.preset]
		sources_specs.extend(preset["sources"])
		extensions_specs.extend(preset["extensions"])

		if args.sources:
			for spec_str in args.sources:
				name, kwargs = parse_spec(spec_str)
				sources_specs.append((name, kwargs))

		if args.extensions:
			for spec_str in args.extensions:
				name, kwargs = parse_spec(spec_str)
				extensions_specs.append((name, kwargs))

		# Override custom source names if provided and using custom preset
		if args.preset == "custom" and args.names:
			# Replace the custom source's names
			sources_specs = [
				(name, {"names": list(args.names)} if name == "custom" else kwargs)
				for name, kwargs in sources_specs
			]

	else:
		if args.sources:
			for spec_str in args.sources:
				name, kwargs = parse_spec(spec_str)
				sources_specs.append((name, kwargs))

		if args.extensions:
			for spec_str in args.extensions:
				name, kwargs = parse_spec(spec_str)
				extensions_specs.append((name, kwargs))

		# If --names was given and a custom source exists, set its names
		if args.names:
			custom_found = False
			for i, (name, kwargs) in enumerate(sources_specs):
				if name == "custom":
					sources_specs[i] = (name, {**kwargs, "names": list(args.names)})
					custom_found = True
					break
			if not custom_found:
				print(
					"Warning: --names provided but no 'custom' source found; adding a custom source with those names.",
					file=sys.stderr,
				)
				sources_specs.append(("custom", {"names": list(args.names)}))

	# Merge: config file provides baseline, CLI args override
	client_kwargs: dict[str, Any] = {**config_client_params}
	client_kwargs["max_concurrency"] = args.max_concurrency
	client_kwargs["max_retries"] = args.max_retries
	client_kwargs["timeout_sec"] = args.timeout
	client_kwargs["rate_per_sec"] = args.rate
	client_kwargs["impersonate"] = args.impersonate
	client_kwargs["paginate_batch_size"] = args.paginate_batch_size

	# Run the pipeline
	asyncio.run(
		run_pipeline(
			sources_specs, extensions_specs, docs_dir, persistance_dir,
			**client_kwargs,
		)
	)


if __name__ == "__main__":
	main()