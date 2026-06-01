"""convert_bookmarks.py
Reads bookmark/bookmark-data.json and produces a .album file.
Also updates site/albums/index.json to include the generated album.

Mappings:
  link                  → screen_name (extracted from skeb URL)
  notes                 → entry.notes
  tags                  → entry.tags
  images                → entry.latest_thumbnails
"""

import json, sys, os, time
from urllib.parse import urlparse

# Ensure we can import album module from parent (src/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from album import AlbumBuilder

ROOT_DIR      = os.path.join(os.path.dirname(__file__), "..")
BOOKMARK_PATH = os.path.join(ROOT_DIR, "bookmark", "bookmark-data.json")
OUTPUT_DIR    = os.path.join(ROOT_DIR, "site", "albums")
INDEX_PATH    = os.path.join(OUTPUT_DIR, "index.json")

def extract_screen_name(link: str) -> str:
    """Extract screen_name from a skeb.jp URL like https://skeb.jp/@username"""
    path = urlparse(link).path
    if path.startswith("/@"):
        return path[2:]
    return path.lstrip("/")

def update_index(album_key: str, label: str, album_type: str, is_file: bool = False):
    """Add or update an album entry in index.json."""
    index = {}
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            index = json.load(f)

    entry = {"label": label, "type": album_type}
    if is_file:
        entry["_file"] = True
    index[album_key] = entry

    # Ensure main_index is present
    if "albums/main_index" not in index:
        index["albums/main_index"] = {"label": "All Artists", "type": "full"}

    # Scan for orphan single .album files in albums/ and auto-index them
    for fname in os.listdir(OUTPUT_DIR):
        if not fname.endswith(".album"):
            continue
        fpath = os.path.join(OUTPUT_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        key = "albums/" + fname.replace(".album", "")
        if key in index:
            continue  # already indexed
        try:
            with open(fpath, "rb") as fh:
                header = fh.read(1024 * 64)
            meta = AlbumBuilder.parse_metadata_from_bytes(header)
            if meta:
                index[key] = {
                    "label": meta.get("label", fname),
                    "type": meta.get("type", "curated"),
                    "_file": True
                }
                print(f"Auto-indexed orphan .album file: {key}")
        except Exception as e:
            print(f"  (skipping {fname}: {e})")

    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Updated index.json with album: {album_key}")

def main():
    if not os.path.exists(BOOKMARK_PATH):
        print(f"Error: bookmark file not found at {BOOKMARK_PATH}")
        sys.exit(1)

    with open(BOOKMARK_PATH, "r", encoding="utf-8") as f:
        bookmarks = json.load(f)

    builder = AlbumBuilder()
    builder.set_name("bookmarks")
    builder.set_label("Bookmarks")
    builder.set_type("reports")
    builder.set_date(time.time())

    for bm in bookmarks:
        sn = extract_screen_name(bm.get("link", ""))
        if not sn:
            continue

        entry = {"screen_name": sn}

        notes = bm.get("notes", "").strip()
        if notes:
            entry["notes"] = notes

        tags = bm.get("tags", [])
        if tags:
            entry["tags"] = tags

        images = bm.get("images", [])
        if images:
            entry["latest_thumbnails"] = images

        builder.add_sparse_entry(entry)

    if builder.is_empty():
        print("No entries to build — empty album.")
        sys.exit(0)

    album_data = builder.build()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "bookmarks.album")

    with open(output_path, "wb") as f:
        f.write(album_data)

    print(f"Written {len(builder.data)} entries to {output_path}")
    print(f"Size: {len(album_data):,} bytes")

    update_index("albums/bookmarks", "Bookmarks", "reports", is_file=True)

if __name__ == "__main__":
    main()
