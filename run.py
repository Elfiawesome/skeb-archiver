from src.pipeline import Pipeline
from src.data_store import DataStore
from src.skeb_client import SkebClient
from src.source.skeb_crawl_source import SkebCrawlSource
from src.source.rescrape_source import RescrapeSource
from src.source.rediscover_source import RediscoverSource
from src.source.custom_source import CustomSource
from src.extension.storage_plugin import StoragePlugin
from src.extension.summary_report_plugin import SummaryReportPlugin
from src.extension.sourcing_limit_plugin import SourcingLimitPlugin
import asyncio

async def main() -> None:
	async with SkebClient() as client:		
		orchestrator = Pipeline(DataStore("docs/skeb"), client)

		orchestrator.add_source(SkebCrawlSource())
		# orchestrator.add_source(RescrapeSource(stale_days=5))
		# orchestrator.add_source(RediscoverSource())
		# orchestrator.add_source(CustomSource(names = ()))
		
		orchestrator.add_extension(StoragePlugin())
		# orchestrator.add_extension(SourcingLimitPlugin(10))
		orchestrator.add_extension(SummaryReportPlugin())

		await orchestrator.run()

if __name__ == "__main__":
	asyncio.run(main())