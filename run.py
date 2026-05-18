from src.pipeline import Pipeline
from src.data_store import DataStore
from src.skeb_client import SkebClient
from src.source.skeb_crawl_source import SkebCrawlSource
from src.source.rescrape_source import RescrapeSource
from src.extension.storage_plugin import StoragePlugin
from src.extension.summary_report_plugin import SummaryReportPlugin
from src.extension.sourcing_limit_plugin import SourcingLimitPlugin
import asyncio

async def main() -> None:
	async with SkebClient() as client:		
		orchestrator = Pipeline(DataStore("docs/skeb"), client)
		orchestrator.sources.append(SkebCrawlSource())
		# orchestrator.sources.append(RescrapeSource())
		orchestrator.extensions.append(StoragePlugin())
		# orchestrator.extensions.append(SourcingLimitPlugin(10))
		orchestrator.extensions.append(SummaryReportPlugin())

		await orchestrator.run()

if __name__ == "__main__":
	asyncio.run(main())