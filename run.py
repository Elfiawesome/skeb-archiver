import argparse
import asyncio
import json

from src.pipeline import Pipeline
from src.data_store import DataStore
from src.skeb_client import SkebClient
from src.registry import create_source, create_extension

PRESETS = {
	"crawl": {
		"sources": [
			{"name": "skeb_crawl"}
		],
		"extensions": [
			{"name": "storage"},
			{"name": "summary_report"}
		]
	}
}

def parse_component_spec(spec: str):
	"""Parse 'name:k1=v1,k2=v2' into (name, kwargs dict)."""
	if ':' in spec:
		name, params_str = spec.split(':', 1)
	else:
		name, params_str = spec, ''
	kwargs = {}
	if params_str:
		for pair in params_str.split(','):
			if '=' in pair:
				k, v = pair.split('=', 1)
				kwargs[k.strip()] = v.strip()
			else:
				raise ValueError(f"Invalid parameter: {pair}")
	return name, kwargs

async def main():
	parser = argparse.ArgumentParser()
	mode_group = parser.add_mutually_exclusive_group()
	mode_group.add_argument("--preset", choices=list(PRESETS.keys()))
	mode_group.add_argument("--config", help="JSON config file")
	mode_group.add_argument("--source", action="append", default=[], metavar="SPEC",
							help="Add a source (e.g., skeb_crawl:genre=art)")
	parser.add_argument("--extension", action="append", default=[], metavar="SPEC",
						help="Add an extension (e.g., storage)")
	args = parser.parse_args()

	# Determine pipeline definition
	if args.preset:
		pipeline_def = PRESETS[args.preset]
		if args.source or args.extension:
			pipeline_def = merge_with_cli(pipeline_def, args.source, args.extension)
	elif args.config:
		import json
		with open(args.config) as f:
			pipeline_def = json.load(f)
	else:
		pipeline_def = {
			"sources": [parse_component_spec(s) for s in args.source],
			"extensions": [parse_component_spec(e) for e in args.extension]
		}

	# Build pipeline
	async with SkebClient() as client:
		store = DataStore(docs_dir="docs", persistance_dir="persistance")
		pipeline = Pipeline(store, client)

		for name, kwargs in pipeline_def["sources"]:
			s = create_source(name, **kwargs)
			pipeline.add_source(s)

		for name, kwargs in pipeline_def.get("extensions", []):
			e = create_extension(name, **kwargs)
			pipeline.add_extension(e)

		await pipeline.run()

def merge_with_cli(preset_def, extra_sources, extra_extensions):
	"""Allow --source and --extension to add to a preset."""
	defs = {"sources": list(preset_def.get("sources", [])),
			"extensions": list(preset_def.get("extensions", []))}
	for spec in extra_sources:
		name, kwargs = parse_component_spec(spec)
		defs["sources"].append({"name": name, "args": kwargs})
	for spec in extra_extensions:
		name, kwargs = parse_component_spec(spec)
		defs["extensions"].append({"name": name, "args": kwargs})
	return defs

if __name__ == "__main__":
	asyncio.run(main())
