# Location Mapping

Takes posts from the Hokkien Mee Facebook group and plots them on an interactive map, so you can browse stalls across Singapore, see what people are saying, and find highly-rated spots near you.

## Why it exists

The Facebook group has thousands of posts but no way to answer "what's the best Hokkien Mee near me?" or "which stalls are people talking about most?" The map turns unstructured social posts into a browsable, geographic view of the community's knowledge.

## User stories

- As a **food hunter**, I want to see all discussed stalls on a map so I can discover places I didn't know about.
- As a **local**, I want to find well-rated stalls near my current location so I don't have to scroll through hundreds of posts.
- As a **researcher**, I want to see which stalls get mentioned most so I can identify community favourites at a glance.
- As a **visitor**, I want to read what people actually said about a stall before I go, so I can set expectations.
- As a **contributor**, I want my post to appear on the map so others can find the stall I'm sharing.

## How it works

### 1. Location extraction
For each post, candidates are collected from multiple sources in priority order:

1. **Facebook check-in** — the `location` field if the author tagged a place
2. **Postal codes** — 6-digit Singapore postal codes found in post text (leading digit 0–8, not `000xxx`)
3. **Known stall aliases** — `LOCATION_ALIASES` in `map_posts.py`, mapping colloquial names to geocodable addresses
4. **Street addresses** — regex patterns for Singapore formats (Block/Blk + street, Lorong, etc.)
5. **Singapore abbreviations** — expands shorthand (AMK → Ang Mo Kio, TPY → Toa Payoh, etc.)

All candidates pass through `location_overrides.json` (excludes, renames, merges) before geocoding.

### 2. Geocoding (two-phase, cached)
Results cached in `output/geocode_cache.json` to avoid redundant API calls:

1. **OneMap API** (primary) — Singapore government geocoder; accurate for HDB blocks, postal codes, hawker centres. Requires `secrets/secrets.py`.
2. **Nominatim/OpenStreetMap** (fallback) — used for POIs and landmarks that OneMap doesn't index.

Results outside Singapore's bounding box (lat 1.15–1.47, lng 103.60–104.05) are rejected. Query variations are tried (with/without abbreviation expansion, stripped suffixes like "Coffee Shop") until one resolves.

### 3. Sentiment scoring
All posts and comments for each stall are scored for sentiment signals. A star rating (1.0–5.0) is computed from the positive/negative signal ratio. Stalls with fewer than 2 signal-bearing texts receive no rating.

### 4. Map generation
1. Posts are grouped by geocoded lat/lng into stall locations.
2. Up to 10 images per post are included (`MAX_IMAGES_PER_POST = 10`).
3. Locations sorted by post count, then alphabetically.
4. JSON payload injected into `map_template.html` by replacing:
   - `__MAP_DATA__` → full payload
   - `__GROUP_URL__` → Facebook group URL
5. Result written to `docs/index.html` — single self-contained file.

## Reference

**Scripts:** `extractor/map_posts.py`, `extractor/location_overrides.json`, `extractor/map_template.html`

**Inputs:**
- `output/group_posts.json` — extracted posts
- `output/image_labels.json` — image classifications (optional)
- `extractor/location_overrides.json` — curated excludes, renames, merges
- `secrets/secrets.py` — OneMap credentials (`onemap` dict with `email` and `password`)

**Outputs:**
- `docs/index.html` — interactive map
- `output/geocode_cache.json` — cached geocoding results

**Location overrides (`location_overrides.json`):**
- `excludes` — location strings to drop entirely
- `renames` — map a string to a corrected canonical name
- `merges` — consolidate duplicate names that resolve to the same stall
