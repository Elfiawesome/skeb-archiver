from pathlib import Path
from typing import AsyncGenerator

from curl_cffi.requests import AsyncSession

from .source import Source
from ..registry import register_source
from ..context import PipelineContext
from ..album import AlbumBuilder
from ..logger import log


@register_source("album")
class AlbumSource(Source):
	def __init__(self, path: str | None = None, paths: list[str] | None = None):
		super().__init__()
		self.paths: list[str] = []
		if path:
			self.paths.append(path)
		if paths:
			self.paths.extend(paths)

	async def get_sources(self, context: PipelineContext) -> AsyncGenerator[str, None]:
		if not self.paths:
			log.warning("AlbumSource has no paths configured.")
			return

		async with AsyncSession() as session:
			for p in self.paths:
				try:
					album = await self._load(session, p)
				except Exception as e:
					log.warning("Album source: failed to load %s: %s", p, e)
					continue

				if album is None:
					log.warning("Album source: could not parse album at %s", p)
					continue

				count = 0
				for entry in album.data:
					if not isinstance(entry, dict):
						continue
					sn = entry.get("screen_name")
					if sn:
						count += 1
						yield sn
				log.info("Album source: loaded %d entries from %s (album=%s)",
					count, p, album.name)

	async def _load(self, session: AsyncSession, p: str) -> AlbumBuilder | None:
		if "://" in p:
			return await self._load_from_url(session, p)
		return AlbumBuilder.load_from_local(Path(p))

	async def _load_from_url(self, session: AsyncSession, url: str) -> AlbumBuilder | None:
		# Markdown album URL
		if url.lower().endswith(".md"):
			r = await session.get(url)
			if r.status_code != 200:
				log.warning("Album source: HTTP %d on %s", r.status_code, url)
				return None
			return AlbumBuilder.parse_markdown(r.text, _basename(url))

		# Single binary .album file (no trailing slash)
		clean = url[:-1] if url.endswith("/") else url
		if clean.lower().endswith(".album"):
			r = await session.get(clean)
			if r.status_code != 200:
				log.warning("Album source: HTTP %d on %s", r.status_code, clean)
				return None
			return AlbumBuilder.unbuild(r.content)

		# Partitioned dir mode: chunks live at {base}.album/{basename}.{1,2,...}
		base = clean[:-len(".album")] if clean.lower().endswith(".album") else clean
		name = base.rsplit("/", 1)[-1]
		chunk_base = f"{base}.album/{name}."

		chunks: list[bytes] = []
		i = 1
		while True:
			r = await session.get(f"{chunk_base}{i}")
			if r.status_code != 200:
				break
			chunks.append(r.content)
			i += 1

		if not chunks:
			log.warning("Album source: no chunks found at %s", chunk_base)
			return None

		return AlbumBuilder.unbuild(b"".join(chunks))


def _basename(url: str) -> str:
	path = url.split("?", 1)[0]
	if path.endswith("/"):
		path = path[:-1]
	return path.rsplit("/", 1)[-1] if "/" in path else path