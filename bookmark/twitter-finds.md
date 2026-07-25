import json
import re
import csv
import time
import sys
import hashlib
import urllib.request
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime

import cloudscraper
import requests
from bs4 import BeautifulSoup

GALLERY_DL_DIR = Path(r"C:\Users\elfia\OneDrive\Desktop\twt\gallery-dl")
OUTPUT_DIR = Path(__file__).parent
EXTRACTED_CP = OUTPUT_DIR / "extracted_urls.json"
BIO_CP = OUTPUT_DIR / "bio_skeb_results.json"
PRICING_CP = OUTPUT_DIR / "skeb_pricing_cache.json"
FINAL_CSV = OUTPUT_DIR / "skeb_users.csv"
FINAL_HTML = OUTPUT_DIR / "skeb_users.html"
FINAL_MD = OUTPUT_DIR / "skeb_album.md"
REQUEST_DELAY = 1.0
ARCHIVER_BASE = "https://elfiawesome.github.io/skeb-archiver/skeb"
PRICING_CONCURRENCY = 20

SKEB_RE = re.compile(r'https?://(?:www\.)?skeb\.jp/@([a-zA-Z0-9_]+)', re.IGNORECASE)
SKEB_HANDLE_RE = re.compile(r'@([a-zA-Z0-9_]+)', re.IGNORECASE)

BIO_DOMAINS = [
    'lit.link', 'tsunagu.cloud', 'vgen.co', 'potofu.me',
    'fori.io', 'carrd.co', 'piku.page', 'linktr.ee'
]
BIO_PATTERN = r'https?://(?:www\.)?(' + '|'.join(d.replace('.', r'\.') for d in BIO_DOMAINS) + r')/[^\s<>"\'\]\)]+'
BIO_LINK_RE = re.compile(BIO_PATTERN, re.IGNORECASE)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}
SCRAPER = cloudscraper.create_scraper()
USERNAME_SAFE_RE = re.compile(r"[^\w\-.]")


def normalize_skeb_url(url):
    match = SKEB_HANDLE_RE.search(url)
    if not match:
        return None, None
    handle = match.group(1)
    return f"https://skeb.jp/@{handle}", handle


def extract_urls(text):
    raw_skeb = [m.group(0) for m in SKEB_RE.finditer(text)]
    skeb_urls = []
    skeb_handles = []
    for raw in raw_skeb:
        norm, handle = normalize_skeb_url(raw)
        if norm and handle:
            if norm not in skeb_urls:
                skeb_urls.append(norm)
                skeb_handles.append(handle)
    bio_urls = list(set(m.group(0) for m in BIO_LINK_RE.finditer(text)))
    return skeb_urls, skeb_handles, bio_urls


def phase1_extract():
    if EXTRACTED_CP.exists():
        print(f"[1/6] Loading checkpoint: {EXTRACTED_CP.name}")
        with open(EXTRACTED_CP, 'r', encoding='utf-8') as f:
            return json.load(f)

    print("[1/6] Scanning JSON files for skeb URLs...")
    authors = {}
    files = sorted(GALLERY_DL_DIR.glob("*.json"))
    total = len(files)

    for i, filepath in enumerate(files):
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{total} files processed, {len(authors)} unique authors found")

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        author = data.get('author') or {}
        author_id = str(author.get('id', ''))
        if not author_id:
            continue
        
        post_date = datetime.fromisoformat(data.get("date"))
        now_date = datetime.now()
        age = now_date - post_date
        if age.days >= 5:
            continue

        

        content = data.get('content', '') or ''
        description = author.get('description', '') or ''
        twitter_handle = (author.get('name', '') or '').strip()
        tweet_date = data.get('date', '') or ''

        if author_id not in authors:
            authors[author_id] = {
                "twitter_id": author_id,
                "twitter_handle": twitter_handle,
                "skeb_urls": [],
                "skeb_handles": [],
                "bio_links": [],
                "tweet_dates": [],
                "tweet_samples": [],
            }

        entry = authors[author_id]
        if twitter_handle and not entry["twitter_handle"]:
            entry["twitter_handle"] = twitter_handle

        urls, handles, _ = extract_urls(content)
        for u, h in zip(urls, handles):
            if u not in entry["skeb_urls"]:
                entry["skeb_urls"].append(u)
                entry["skeb_handles"].append(h)

        _, handles_bio, bio_links = extract_urls(description)
        # Re-extract full skeb URLs from bio
        for m in SKEB_RE.finditer(description):
            norm, handle = normalize_skeb_url(m.group(0))
            if norm and handle and norm not in entry["skeb_urls"]:
                entry["skeb_urls"].append(norm)
                entry["skeb_handles"].append(handle)

        for link in bio_links:
            if link not in entry["bio_links"]:
                entry["bio_links"].append(link)

        if tweet_date:
            entry["tweet_dates"].append(tweet_date)
        if content:
            preview = content[:300].replace('\n', ' ').strip()
            if preview not in entry["tweet_samples"]:
                entry["tweet_samples"].append(preview)

    for entry in authors.values():
        entry["bio_links"] = list(set(entry["bio_links"]))
        entry["tweet_dates"] = sorted(set(entry["tweet_dates"]), reverse=True)
        entry["tweet_samples"] = entry["tweet_samples"][:3]

    with open(EXTRACTED_CP, 'w', encoding='utf-8') as f:
        json.dump(authors, f, ensure_ascii=False, indent=2)

    with_skeb = sum(1 for a in authors.values() if a["skeb_handles"])
    with_bio = sum(1 for a in authors.values() if a["bio_links"])
    print(f"  Done. {len(authors)} unique authors ({with_skeb} with skeb, {with_bio} with bio links)")
    return authors


def phase2_follow_bio_links(authors):
    if BIO_CP.exists():
        print(f"[2/6] Loading checkpoint: {BIO_CP.name}")
        with open(BIO_CP, 'r', encoding='utf-8') as f:
            return json.load(f)

    print("[2/6] Following bio links to find skeb URLs...")
    results = {}

    candidates = [
        (aid, entry) for aid, entry in authors.items()
        if not entry["skeb_handles"]
        and entry["bio_links"]
    ]
    print(f"  {len(candidates)} authors to check via bio links")

    for i, (aid, entry) in enumerate(candidates):
        skeb_found = []
        for bio_url in entry["bio_links"]:
            try:
                resp = SCRAPER.get(bio_url, headers=HEADERS, timeout=15)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'lxml')
                    for a_tag in soup.find_all('a', href=True):
                        href = a_tag['href']
                        norm, handle = normalize_skeb_url(href)
                        if norm and handle and norm not in skeb_found:
                            skeb_found.append(norm)
            except Exception as e:
                print(f"  Error: {bio_url} -> {e}")

        if skeb_found:
            results[aid] = skeb_found

        if (i + 1) % 50 == 0 or i == 0:
            print(f"  [{i+1}/{len(candidates)}] Found {len(results)} so far")

    with open(BIO_CP, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"  Done. Found skeb for {len(results)} authors via bio links")
    return results


def skeb_filename(handle):
    safe = USERNAME_SAFE_RE.sub("_", handle)
    h = hashlib.md5(handle.encode('utf-8')).hexdigest()[:6]
    return f"{safe}-{h}.json"


def fetch_single_price(handle, results_dict, lock):
    filename = skeb_filename(handle)
    url = f"{ARCHIVER_BASE}/{filename}"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        profile = data.get("profile", {})
        skills = profile.get("skills", [])
        prices = {}
        for sk in skills:
            genre = sk.get("genre", "unknown")
            amt = sk.get("default_amount")
            if amt is not None:
                prices[genre] = amt
        with lock:
            results_dict[handle] = {
                "skills": skills,
                "prices": prices,
                "acceptable": profile.get("acceptable"),
                "nsfw_acceptable": profile.get("nsfw_acceptable"),
                "works_count": profile.get("received_works_count"),
            }
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            with lock:
                results_dict[handle] = None
            return False
        return False
    except Exception:
        return False


def phase3_fetch_prices(authors, bio_results):
    if PRICING_CP.exists():
        print(f"[3/6] Loading checkpoint: {PRICING_CP.name}")
        with open(PRICING_CP, 'r', encoding='utf-8') as f:
            return json.load(f)

    print("[3/6] Fetching pricing from skeb-archiver...")

    all_handles = set()
    for entry in authors.values():
        for h in entry["skeb_handles"]:
            all_handles.add(h)
    for aid, urls in bio_results.items():
        for url in urls:
            _, handle = normalize_skeb_url(url)
            if handle:
                all_handles.add(handle)

    all_handles = sorted(all_handles)
    print(f"  {len(all_handles)} unique skeb handles to look up")

    results = {}
    lock = Lock()
    fetched = 0
    found = 0

    with ThreadPoolExecutor(max_workers=PRICING_CONCURRENCY) as ex:
        futures = {ex.submit(fetch_single_price, h, results, lock): h for h in all_handles}
        for future in as_completed(futures):
            fetched += 1
            if future.result():
                found += 1
            if fetched % 500 == 0 or fetched == len(all_handles):
                print(f"  [{fetched}/{len(all_handles)}] Found {found} with pricing")

    with open(PRICING_CP, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"  Done. Found pricing for {found}/{len(all_handles)} handles")
    return results


def get_all_genres(pricing_data):
    genres = set()
    for v in pricing_data.values():
        if v and v.get("prices"):
            genres.update(v["prices"].keys())
    return sorted(genres)


def phase4_output(authors, bio_results, pricing_data):
    print("[4/6] Writing CSV with pricing...")

    all_genres = get_all_genres(pricing_data)

    rows = []
    writer_lock = Lock()

    def process_author(aid, entry):
        local_rows = []
        seen_pairs = set()

        sources = []
        for url in entry["skeb_urls"]:
            sources.append(("tweet_content", url))
        if aid in bio_results:
            for url in bio_results[aid]:
                norm, _ = normalize_skeb_url(url)
                if norm:
                    sources.append(("via_bio_link", norm))

        if not sources:
            return []

        for src_type, skeb_url in sources:
            norm_url, handle = normalize_skeb_url(skeb_url)
            if not handle:
                continue
            pair = (aid, handle)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            pricing = pricing_data.get(handle)
            row = {
                "twitter_id": aid,
                "twitter_handle": entry["twitter_handle"],
                "skeb_handle": handle,
                "skeb_url": norm_url,
                "source_type": src_type,
                "acceptable": "",
                "nsfw_acceptable": "",
                "works_count": "",
                "tweet_date": entry["tweet_dates"][0] if entry["tweet_dates"] else "",
                "tweet_preview": entry["tweet_samples"][0] if entry["tweet_samples"] else "",
            }
            for g in all_genres:
                row[f"price_{g}"] = ""

            if pricing:
                row["acceptable"] = pricing.get("acceptable", "")
                row["nsfw_acceptable"] = pricing.get("nsfw_acceptable", "")
                row["works_count"] = pricing.get("works_count", "")
                for g, amt in pricing.get("prices", {}).items():
                    row[f"price_{g}"] = amt

            local_rows.append(row)

        return local_rows

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(process_author, aid, entry): aid for aid, entry in authors.items()}
        for future in as_completed(futures):
            result = future.result()
            if result:
                rows.extend(result)

    fieldnames = [
        "twitter_id", "twitter_handle", "skeb_handle", "skeb_url",
        "source_type", "acceptable", "nsfw_acceptable", "works_count",
    ] + [f"price_{g}" for g in all_genres] + [
        "tweet_date", "tweet_preview"
    ]

    rows.sort(key=lambda r: r["skeb_handle"])

    with open(FINAL_CSV, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  Written {len(rows)} rows to {FINAL_CSV.name}")
    return rows


def phase5_generate_html(rows):
    print("[5/6] Generating HTML viewer...")

    price_cols = [k for k in rows[0].keys() if k.startswith("price_")] if rows else []

    html_rows = []
    for r in rows:
        acceptable = r.get("acceptable", "")
        nsfw = r.get("nsfw_acceptable", "")
        works = r.get("works_count", "")
        tweet_date = r.get("tweet_date", "")
        preview = r.get("tweet_preview", "")
        preview_escaped = preview.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")

        prices = {}
        for c in price_cols:
            v = r.get(c, "")
            prices[c] = int(v) if v else ""

        html_rows.append({
            "tid": r["twitter_id"],
            "handle": r["twitter_handle"],
            "skeb": r["skeb_handle"],
            "src": r["source_type"],
            "accept": acceptable,
            "nsfw": nsfw,
            "works": int(works) if works else "",
            "date": tweet_date,
            "preview": preview_escaped,
            "prices": prices,
        })

    genres = [c.replace("price_", "") for c in price_cols]

    html_parts = []
    html_parts.append('''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>skeb users</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px}
h1{font-size:20px;margin-bottom:12px;color:#f0f6fc}
.controls{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-bottom:12px}
.controls label{color:#8b949e;font-size:13px}
.controls input,.controls select{padding:5px 8px;border:1px solid #30363d;border-radius:6px;background:#161b22;color:#c9d1d9;font-size:13px}
.controls input:focus,.controls select:focus{outline:none;border-color:#58a6ff}
.controls .counter{margin-left:auto;color:#8b949e;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:6px 10px;text-align:left;border-bottom:1px solid #21262d;white-space:nowrap}
th{position:sticky;top:0;background:#161b22;cursor:pointer;user-select:none;color:#8b949e;font-weight:600;z-index:2}
th:hover{color:#f0f6fc}
th.sorted{color:#58a6ff}
th .arrow{margin-left:4px;font-size:11px}
tr:hover td{background:#1c2128}
td a{color:#58a6ff;text-decoration:none}
td a:visited{color:#b392f0!important}
td a:hover{text-decoration:underline;color:#79c0ff}
td.numeric{text-align:right;font-variant-numeric:tabular-nums}
td.price{font-weight:600}
td.price.yes{color:#7ee787}
td.price.mid{color:#d29922}
td.price.high{color:#f85149}
td.accept{font-size:12px}
td.accept.y{color:#7ee787}
td.accept.n{color:#f85149}
td.src{font-size:11px;color:#8b949e;font-style:italic}
td.date{color:#8b949e;font-size:12px}
td.preview{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#8b949e;font-size:12px}
@media(max-width:900px){.hide-mobile{display:none}}
</style>
</head>
<body>
<h1>skeb users <span id="count" style="font-weight:400;font-size:14px;color:#8b949e"></span></h1>
<div class="controls">
  <label>search <input id="search" type="text" placeholder="any column..." autofocus></label>
  <label>source <select id="srcFilter"><option value="">all</option><option value="tweet_content">tweet</option><option value="via_bio_link">bio link</option></select></label>
  <label>accepting <select id="acceptFilter"><option value="">all</option><option value="True">yes</option><option value="False">no</option></select></label>
  <label>min price <input id="minPrice" type="number" min="0" step="1000" placeholder="0" style="width:90px"></label>
  <label>genre <select id="genreFilter"><option value="">all</option></select></label>
  <span class="counter" id="counter"></span>
</div>
<div style="overflow-x:auto;max-height:calc(100vh - 140px)">
<table>
<thead><tr id="headerRow"></tr></thead>
<tbody id="tbody"></tbody>
</table>
</div>
<script>
const DATA = DATA_PLACEHOLDER;
const GENRES = GENRES_PLACEHOLDER;

function esc(t){if(t===null||t===undefined)return'';return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}

const cols = [
  {key:'skeb',label:'skeb',link:r=>'https://skeb.jp/@'+esc(r.skeb)},
  {key:'handle',label:'twitter',link:r=>'https://x.com/'+esc(r.handle)},
  {key:'tid',label:'twitter_id',hideMobile:true},
  {key:'src',label:'source'},
  {key:'accept',label:'accepting',className:'accept'},
  {key:'nsfw',label:'nsfw',className:'accept',hideMobile:true},
  {key:'works',label:'works',className:'numeric'},
  ...GENRES.map(g=>({key:'price_'+g,label:g,className:'numeric price',price:true})),
  {key:'date',label:'date',className:'date',hideMobile:true},
  {key:'preview',label:'preview',className:'preview',hideMobile:true},
];

let sortCol = 'skeb';
let sortDir = 1;
let filtered = [];

function getVal(r,col) {
  if(col.price) {
    const v=r.prices['price_'+col.label];
    return v===''?-1:v;
  }
  let v=r[col.key];
  if(col.key==='works') return v===''?-1:v;
  if(col.key==='accept'||col.key==='nsfw') return v==='True'?1:v==='False'?0:-1;
  return String(v).toLowerCase();
}

function render() {
  const q = document.getElementById('search').value.toLowerCase();
  const src = document.getElementById('srcFilter').value;
  const acc = document.getElementById('acceptFilter').value;
  const minP = parseInt(document.getElementById('minPrice').value)||0;
  const genre = document.getElementById('genreFilter').value;

  filtered = DATA.filter(r => {
    if(src && r.src!==src) return false;
    if(acc && String(r.accept)!==acc) return false;
    if(genre) {
      const v = r.prices['price_'+genre];
      if(v===''||v<minP) return false;
    } else if(minP) {
      const has = Object.values(r.prices).some(v => v!=='' && v>=minP);
      if(!has) return false;
    }
    if(!q) return true;
    const searchable = [r.skeb,r.handle,r.tid,r.src,r.accept,r.nsfw,String(r.works),r.date,r.preview];
    GENRES.forEach(g => searchable.push(String(r.prices['price_'+g])));
    return searchable.some(s => String(s).toLowerCase().includes(q));
  });

  filtered.sort((a,b) => {
    const col = cols.find(c => c.key === sortCol);
    const va = getVal(a, col), vb = getVal(b, col);
    if(typeof va==='number'&&typeof vb==='number') return (va-vb)*sortDir;
    return String(va).localeCompare(String(vb))*sortDir;
  });

  document.getElementById('count').textContent = '\u2014 '+filtered.length+' rows';

  const hdr = document.getElementById('headerRow');
  hdr.innerHTML = cols.map(c => 
    '<th class="'+(c.hideMobile?'hide-mobile ':'')+(sortCol===c.key?'sorted':'')+'" data-key="'+c.key+'">'+
    esc(c.label)+'<span class="arrow">'+(sortCol===c.key?(sortDir>0?'\u25B2':'\u25BC'):'')+'</span></th>'
  ).join('');

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = filtered.map(r => {
    let cells = cols.map(c => {
      let val = '', cls = c.className||'', link = null;
      if(c.link) {
        val = esc(r.skeb);
        if(c.key==='skeb') val = esc(r.skeb);
        else if(c.key==='handle') val = esc(r.handle);
        link = c.link(r);
      } else if(c.price) {
        const v = r.prices['price_'+c.label];
        val = v!==''?'\u00A5'+v.toLocaleString():'\u2014';
        if(v!=='') cls += ' '+(v<5000?'yes':v<15000?'mid':'high');
      } else if(c.key==='accept'||c.key==='nsfw') {
        val = r[c.key]==='True'?'yes':r[c.key]==='False'?'no':'\u2014';
        cls += ' '+(r[c.key]==='True'?'y':'n');
      } else if(c.key==='works') {
        val = r.works!==''?r.works:'\u2014';
      } else if(c.key==='date') {
        val = esc(r.date);
      } else if(c.key==='preview') {
        val = esc(r.preview);
      } else {
        val = esc(r[c.key]);
      }
      const tdClass = (c.hideMobile?'hide-mobile ':'')+cls;
      if(link) return '<td class="'+tdClass+'"><a href="'+esc(link)+'" target="_blank">'+val+'</a></td>';
      return '<td class="'+tdClass+'">'+val+'</td>';
    }).join('');
    return '<tr>'+cells+'</tr>';
  }).join('');

  document.getElementById('counter').textContent = filtered.length+' / '+DATA.length+' rows';
}

document.addEventListener('click', e => {
  const th = e.target.closest('th');
  if(!th) return;
  const key = th.dataset.key;
  if(key===sortCol) sortDir*=-1;
  else { sortCol=key; sortDir=1; }
  render();
});

['search','srcFilter','acceptFilter','minPrice','genreFilter'].forEach(id => 
  document.getElementById(id).addEventListener('input', render)
);

const sel = document.getElementById('genreFilter');
GENRES.forEach(g => {
  const opt = document.createElement('option');
  opt.value = g;
  opt.textContent = g;
  sel.appendChild(opt);
});

render();
</script>
</body>
</html>''')

    data_json = json.dumps(html_rows, ensure_ascii=False)
    genres_json = json.dumps(genres, ensure_ascii=False)

    html = ''.join(html_parts).replace("DATA_PLACEHOLDER", data_json).replace("GENRES_PLACEHOLDER", genres_json)

    with open(FINAL_HTML, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"  Written {FINAL_HTML.name}")
    return html_rows


def phase6_generate_markdown_album(authors, bio_results, pricing_data):
    print("[6/6] Generating markdown album...")

    all_handles = set()
    for entry in authors.values():
        for h in entry["skeb_handles"]:
            all_handles.add(h)
    for aid, urls in bio_results.items():
        for url in urls:
            _, handle = normalize_skeb_url(url)
            if handle:
                all_handles.add(handle)

    seen = set()
    lines = []
    for handle in sorted(all_handles):
        if handle in seen:
            continue
        seen.add(handle)
        lines.append(f"# https://skeb.jp/@{handle}")
        pricing = pricing_data.get(handle)
        if pricing and pricing.get("prices"):
            parts = []
            for genre, amt in sorted(pricing["prices"].items()):
                parts.append(f"{genre}: \u00A5{amt:,}")
            if parts:
                lines.append("  " + " \u00B7 ".join(parts))
        lines.append("")

    content = "\n".join(lines)

    with open(FINAL_MD, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  Written {len(seen)} entries to {FINAL_MD.name}")
    return seen


def print_summary(authors, bio_results, pricing_data, rows):
    direct = sum(1 for a in authors.values() if a["skeb_handles"])
    via_bio = len(bio_results)
    with_pricing = sum(1 for v in pricing_data.values() if v is not None)
    no_skeb = sum(1 for a in authors.values()
                  if not a["skeb_handles"]
                  and a.get("twitter_id") not in bio_results)

    total_handles = len(set(
        h for a in authors.values() for h in a["skeb_handles"]
    ).union(
        normalize_skeb_url(url)[1] for urls in bio_results.values() for url in urls if normalize_skeb_url(url)[1]
    ))

    print("\n=== Summary ===")
    print(f"  Total unique authors:        {len(authors)}")
    print(f"  With skeb (direct):           {direct}")
    print(f"  Found via bio link follow:    {via_bio}")
    print(f"  Without any skeb link:        {no_skeb}")
    print(f"  Total unique skeb handles:    {total_handles}")
    print(f"  Pricing found:                {with_pricing}/{total_handles}")
    print(f"  Output rows:                  {len(rows)}")
    print(f"\nOutput: {FINAL_CSV}")
    print(f"Output: {FINAL_HTML}")
    print(f"Output: {FINAL_MD}")


def main():
    authors = phase1_extract()
    bio_results = phase2_follow_bio_links(authors)
    pricing_data = phase3_fetch_prices(authors, bio_results)
    rows = phase4_output(authors, bio_results, pricing_data)
    phase5_generate_html(rows)
    phase6_generate_markdown_album(authors, bio_results, pricing_data)
    print_summary(authors, bio_results, pricing_data, rows)


if __name__ == "__main__":
    main()
