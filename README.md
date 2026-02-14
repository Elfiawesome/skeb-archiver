# Skeb Price Tracker

Crawls [Skeb.jp](https://skeb.jp) for artist profiles, commission
prices, and completed works.  Tracks price changes over time.
Publishes a browsable dark-mode static site via GitHub Pages.

## Data flow

```
┌──────────┐      ┌────────────────┐      ┌──────────────────────┐
│ Skeb API │─────▸│ src/crawler.py │─────▸│ skeb/<user>.json     │
└──────────┘      └────────────────┘      │  (raw per-user data) │
                                          └──────────┬───────────┘
                                                     │
                                          ┌──────────▼───────────┐
                                          │ src/site.py          │
                                          └──────────┬───────────┘
                                                     │
                              ┌───────────────────────┼──────────────┐
                              ▼                       ▼              │
                  docs/api/index.json    docs/api/users/<name>.json  │
                  (table summary)        (full detail, lazy-loaded)  │
                              │                       │              │
                              └───────────┬───────────┘              │
                                          ▼                          │
                              docs/index.html + app.js ◂─────────────┘
                              (dark-mode static site)
```

## Quick start (local)

```bash
pip install -r requirements.txt
python -m src.main
# open docs/index.html in a browser
```

## Google Colab

```python
# ── cell 1: clone ───────────────────────────────────────
!pip install aiohttp
TOKEN = "ghp_XXXXXXXXXXXX"           # PAT with repo scope
REPO  = "your-user/skeb-tracker"
!git clone https://{TOKEN}@github.com/{REPO}.git repo
%cd repo

# ── cell 2: crawl ──────────────────────────────────────
from src.crawler import SkebCrawler
from src.site import generate_data

crawler = SkebCrawler(data_dir="skeb", max_items=-1)
await crawler.run()
generate_data(data_dir="skeb", output_dir="docs")

# ── cell 3: push ───────────────────────────────────────
!git config user.name  "colab-bot"
!git config user.email "colab-bot@users.noreply.github.com"
!git add skeb/ docs/api/
!git diff --cached --quiet || git commit -m "data: crawl $(date -u +%Y-%m-%dT%H:%M:%SZ)"
!git push
```

## GitHub Actions

The workflow at `.github/workflows/crawl.yml` runs daily at
06:00 UTC.  Trigger manually from **Actions → Run workflow**.

## GitHub Pages

1. **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`   Folder: `/docs`
4. Site appears at `https://<user>.github.io/<repo>/`

## Data format

Each `skeb/<user>.json` (raw):

```json
{
  "screen_name": "artist",
  "first_seen":  "2025-06-01T12:00:00+00:00",
  "last_updated":"2025-07-14T08:00:00+00:00",
  "profile": {},
  "price_history": {
    "art": [
      {"amount": 5000, "recorded_at": "2025-06-01T12:00:00+00:00"},
      {"amount": 8000, "recorded_at": "2025-07-14T08:00:00+00:00"}
    ]
  },
  "works": [
    {"path": "/@artist/works/123", "scraped_at": "2025-06-01T..."}
  ]
}
```

`docs/api/index.json` (generated, lightweight):

```json
{
  "generated_at": "...",
  "user_count": 1234,
  "users": [
    {
      "screen_name": "artist",
      "file": "artist",
      "avatar_url": "https://...",
      "works_count": 15,
      "current_prices": {"art": 8000},
      "price_range": {"art": {"min": 5000, "max": 8000}},
      "first_seen": "...",
      "last_updated": "..."
    }
  ]
}
```

`docs/api/users/artist.json` (generated, full — loaded on demand):

```json
{
  "screen_name": "artist",
  "name": "Display Name",
  "avatar_url": "...",
  "price_history": { "art": [...] },
  "current_prices": { "art": 8000 },
  "price_range": { "art": {"min": 5000, "max": 8000} },
  "works": [
    {"path": "...", "preview": "https://...", "genre": "art", "created_at": "..."}
  ]
}
```

Price history entries are appended **only when the amount changes**.