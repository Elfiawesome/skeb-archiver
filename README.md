# Skeb Price Tracker

Crawls [Skeb.jp](https://skeb.jp) for artist profiles, commission prices,
and completed works.  Tracks price changes over time and publishes a
browsable static site via GitHub Pages.

## Project layout

```
skeb/            per-user JSON data (one file each)
docs/            static site (GitHub Pages)
index.html
style.css
app.js
data.json      generated from skeb/*.json
src/             crawler source
```

## Quick start (local)

```bash
pip install -r requirements.txt
python -m src.main          # crawl + generate docs/data.json
```

Then open `docs/index.html` in a browser.

## Google Colab

```python
# ── cell 1: setup ────────────────────────────────────────
!pip install aiohttp
# Use a personal access token with repo scope
TOKEN  = "ghp_XXXXXXXXXXXX"
REPO   = "your-username/skeb-tracker"
!git clone https://{TOKEN}@github.com/{REPO}.git repo
%cd repo

# ── cell 2: crawl ───────────────────────────────────────
from src.crawler import SkebCrawler
from src.site import generate_data

crawler = SkebCrawler(data_dir="skeb", max_items=-1)
await crawler.run()
generate_data()

# ── cell 3: commit & push ───────────────────────────────
!git config user.name  "colab-bot"
!git config user.email "colab-bot@users.noreply.github.com"
!git add skeb/ docs/data.json
!git diff --cached --quiet || git commit -m "data: crawl $(date -u +%Y-%m-%dT%H:%M:%SZ)"
!git push
```

## GitHub Actions (automatic)

The workflow at `.github/workflows/crawl.yml` runs daily at 06:00 UTC.
Trigger it manually from the **Actions** tab → **Run workflow**.

## GitHub Pages

1. Go to **Settings → Pages**
2. Set source to **Deploy from a branch**
3. Branch: `main`, folder: `/docs`
4. The site will be at `https://<user>.github.io/<repo>/`

## Data format

Each `skeb/<username>.json`:

```json
{
"screen_name": "artist",
"first_seen":  "2025-06-01T12:00:00+00:00",
"last_updated":"2025-07-14T08:00:00+00:00",
"profile":     { },
"price_history": {
	"art": [
	{ "amount": 5000, "recorded_at": "2025-06-01T12:00:00+00:00" },
	{ "amount": 8000, "recorded_at": "2025-07-14T08:00:00+00:00" }
	]
},
"works": [
	{ "path": "/@artist/works/123", "scraped_at": "2025-06-01T..." }
]
}
```

Price history entries are only appended when the price **actually changes**.