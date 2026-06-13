from ...context import PipelineContext
from ...event.event import *
from ..extension_plugin import ExtensionPlugin
from ...registry import register_extension
from ...album import AlbumBuilder
from ...logger import log

@register_extension("price_drop_album")
class PriceDropAlbumPlugin(ExtensionPlugin):
	priority = 100

	def __init__(self, genre: str, min_drop: int = 0):
		super().__init__()
		self.genre = genre
		self.min_drop = min_drop

	def on_event(self, context: PipelineContext, event: Event):

		if not isinstance(event, EndEvent):
			return

		album = AlbumBuilder() \
			.set_name(f"price_drop_{self.genre}") \
			.set_label(f"Price Drop: {self.genre} (>=¥{self.min_drop})") \
			.set_type("curated")

		report_lines = []
		report_lines.append(f" --- PRICE DROP REPORT: {self.genre} (>=¥{self.min_drop}) ---")
		report_lines.append("")

		for user_data in context.store.load_all():
			price_history = user_data.get("price_history", {})
			if not isinstance(price_history, dict):
				continue

			history = price_history.get(self.genre, [])
			if not isinstance(history, list) or len(history) < 2:
				continue

			prev_amount = history[-2].get("amount")
			latest_amount = history[-1].get("amount")
			if prev_amount is None or latest_amount is None:
				continue

			drop = prev_amount - latest_amount
			if drop >= self.min_drop:
				album.add_entry(user_data)
				screen_name = user_data.get("screen_name", "unknown")
				prev_time = history[-2].get("recorded_at", 0)
				latest_time = history[-1].get("recorded_at", 0)
				report_lines.append(f"  {screen_name}: ¥{prev_amount} -> ¥{latest_amount} (drop: ¥{drop})")
				report_lines.append(f"    recorded: {prev_time} -> {latest_time}")
				report_lines.append("")

		report_lines.append(f" --- Total users with price drop: {len(album.data)} ---")
		log_text = "\n".join(report_lines)
		log.info(log_text)

		session_folder = context.store.open_session_date_folder()
		report_path = session_folder / f"price_drop_{self.genre}.txt"
		with report_path.open("w", encoding="utf-8") as f:
			f.write(log_text)

		if not album.is_empty():
			album.set_date(context.store.timestamp_now())
			album.build()
			context.store.store_album(album, session_folder)
