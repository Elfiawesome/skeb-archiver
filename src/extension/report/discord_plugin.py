import asyncio
import json
from typing import Any

from curl_cffi.requests import AsyncSession

from ...context import PipelineContext
from ...event.event import Event, ProfileFetchedEvent, EndEvent
from ..extension_plugin import ExtensionPlugin
from ...registry import register_extension
from ...logger import log


@register_extension("discord_report")
class DiscordReportPlugin(ExtensionPlugin):
	priority = 100

	MIN_SEND_GAP = 2.0
	MAX_RETRY = 2

	def __init__(self, webhook_url: str, max_price: int = 1000, genre: str | None = None, max_images: int = 1, target_genre: str = "art"):
		super().__init__()
		self.webhook_url = webhook_url
		self.max_price = max_price
		self.genre = genre
		self.max_images = max(1, max(max_images, 1))
		self.target_genre = target_genre

		# Lazily initialized on first event (need running loop)
		self._session: AsyncSession | None = None
		self._lock: asyncio.Lock | None = None
		self._last_send: float = 0.0
		self._pending: set[asyncio.Task] = set()

	def _ensure_runtime(self) -> None:
		if self._session is None:
			self._session = AsyncSession()
			self._lock = asyncio.Lock()

	def on_event(self, context: PipelineContext, event: Event):
		if isinstance(event, ProfileFetchedEvent):
			payload = self._build_payload(event.data)
			if payload is None: return
			self._ensure_runtime()
			task = asyncio.create_task(self._send(payload))
			self._pending.add(task)
			task.add_done_callback(self._pending.discard)

		if isinstance(event, EndEvent):
			self._ensure_runtime()
			asyncio.create_task(self._drain())

	def _build_payload(self, profile: dict[str]) -> dict[str, Any] | None:
		if not isinstance(profile, dict): return None
		screen_name = profile.get("screen_name")
		if not screen_name: return None

		skills = profile.get("skills", [])
		if not isinstance(skills, list): return None

		qualifying: list[tuple[str, Any]] = []
		for sk in skills:
			if not isinstance(sk, dict): continue
			genre = sk.get("genre")
			if genre == self.target_genre or self.target_genre == "all":
				if self.genre is not None and genre != self.genre: continue
				amount = sk.get("default_amount")
				if amount is None: continue
				if amount < self.max_price:
					qualifying.append((genre or "unknown", amount))

		if not qualifying: return None

		# Build Discord embeds (max 10 per message). 1st embed = artist card,
		# remaining embeds = work samples (up to max_images).
		avatar_url = profile.get("avatar_url", "") or ""
		base_profile_url = f"https://skeb.jp/@{screen_name}"

		price_summary = ", ".join(f"{g}: \u00A5{a:,}" for g, a in qualifying)
		thumbnail_urls = self._extract_work_thumbnails(profile, self.max_images)

		embeds: list[dict[str, Any]] = []

		# Embed 1: artist card
		artist_embed: dict[str, Any] = {
			"title": f"@{screen_name}",
			"url": base_profile_url,
			"color": 0xFFC857,
			"fields": [
				{"name": "Price", "value": price_summary, "inline": False},
			],
			"footer": {"text": f"<\u00A5{self.max_price:,}"},
		}
		if avatar_url:
			artist_embed["thumbnail"] = {"url": avatar_url}
		if thumbnail_urls:
			artist_embed["image"] = {"url": thumbnail_urls[0]}
		embeds.append(artist_embed)

		# Embeds 2-N: additional work samples
		for url in thumbnail_urls[1:]:
			embeds.append({"image": {"url": url}, "color": 0xFFC857})
			if len(embeds) >= 10: break

		return {"embeds": embeds}

	@staticmethod
	def _extract_work_thumbnails(profile: dict[str], max_count: int) -> list[str]:
		works = profile.get("received_works")
		if not isinstance(works, list): return []

		urls: list[str] = []
		for w in works:
			if not isinstance(w, dict): continue
			thumb = DiscordReportPlugin._extract_thumbnail(w)
			if thumb["src"]:
				urls.append(DiscordReportPlugin._pick_best_url(thumb["srcset"], thumb["src"]))
				if len(urls) >= max_count: break
		return urls

	@staticmethod
	def _extract_thumbnail(work: dict[str]) -> dict[str, str]:
		for key in ("thumbnail_image_urls", "private_thumbnail_image_urls"):
			urls = work.get(key)
			if isinstance(urls, dict) and urls.get("src"):
				return {"src": urls["src"], "srcset": urls.get("srcset", "")}
		return {"src": "", "srcset": ""}

	@staticmethod
	def _pick_best_url(srcset: str, fallback: str = "") -> str:
		if not srcset:
			return fallback
		parts = [p.strip() for p in srcset.split(",") if p.strip()]
		for target in ("3x", "2x"):
			for part in parts:
				tokens = part.rsplit(None, 1)
				if len(tokens) == 2 and tokens[1] == target:
					return tokens[0]
		if parts:
			return parts[0].split()[0]
		return fallback

	async def _send(self, payload: dict[str, Any]) -> None:
		assert self._lock is not None and self._session is not None
		async with self._lock:
			# Pace at MIN_SEND_GAP (Discord 30msg/60s = 2s gap is sustainable)
			now = asyncio.get_event_loop().time()
			wait = self._last_send + self.MIN_SEND_GAP - now
			if wait > 0:
				await asyncio.sleep(wait)

			for attempt in range(1, self.MAX_RETRY + 1):
				try:
					r = await self._session.post(
						self.webhook_url,
						json=payload,
						headers={"Content-Type": "application/json"},
						timeout=30,
					)

					if r.status_code == 429:
						retry_after = 2.0
						try:
							body = r.json()
							raw = body.get("retry_after")
							if isinstance(raw, (int, float)):
								retry_after = float(raw)
						except Exception:
							pass
						log.warning("Discord 429, retrying after %.1fs (attempt %d/%d)",
							retry_after, attempt, self.MAX_RETRY)
						await asyncio.sleep(retry_after)
						continue

					if r.status_code in (200, 204):
						self._last_send = asyncio.get_event_loop().time()
						return

					log.warning("Discord webhook non-OK: HTTP %d (attempt %d/%d): %s",
						r.status_code, attempt, self.MAX_RETRY, r.text[:200])
					if attempt < self.MAX_RETRY:
						await asyncio.sleep(2 ** attempt)
						continue
					return

				except Exception as e:
					log.warning("Discord send error (attempt %d/%d): %s",
						attempt, self.MAX_RETRY, e)
					if attempt < self.MAX_RETRY:
						await asyncio.sleep(2 ** attempt)
						continue
					return

	async def _drain(self) -> None:
		# Best-effort wait for in-flight sends before pipeline exits.
		if not self._pending: return
		pending = list(self._pending)
		log.info("Discord drain: awaiting %d in-flight send(s)", len(pending))
		try:
			await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=30.0)
		except asyncio.TimeoutError:
			log.warning("Discord drain timed out, some messages may be lost.")
		if self._session is not None:
			try:
				await self._session.close()
			except Exception:
				pass
			self._session = None