# hokkien-mee

Visualising Hokkien Mee in Singapore.

Data is extracted from the public Facebook group: [Hokkien Mee (227074250721100)](https://www.facebook.com/groups/227074250721100/)

---

## Setup

### 1. Prerequisites

- Python 3.9+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- A Facebook account (needed for cookies)
- A free [OneMap API account](https://www.onemap.gov.sg/apidocs/register) (needed for mapping)

### 2. Install dependencies

```bash
uv sync
uv run playwright install chromium
```

### 3. Export your Facebook cookies

The scraper needs your browser cookies to access the group.

1. Install the **"Get cookies.txt LOCALLY"** browser extension:
   - [Chrome](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. Log into [facebook.com](https://www.facebook.com) in your browser.
3. While on **www.facebook.com**, click the extension icon and **export as Netscape** format.
4. Save the file as `facebook_cookies.txt` in the project root (same level as this README).

> **Note:** Cookies expire after some time. If you get login errors, re-export a fresh cookies file.

### 4. Set up OneMap API credentials

The mapping script uses [OneMap](https://www.onemap.gov.sg/) to geocode addresses.

1. Register for a free account at https://www.onemap.gov.sg/apidocs/register
2. Create `secrets/secrets.py`:

```python
onemap = {
    "email": "your_email@example.com",
    "password": "your_password"
}
```

---

## Quick start

Once setup is complete, run the full pipeline (extract → download images → map):

```bash
./run.sh
```

Or run individual steps:

```bash
./run.sh extract           # extract posts only
./run.sh extract --pages 20  # extract with options
./run.sh images            # download images only
./run.sh map               # generate map only
./run.sh help              # show usage
```

---

## Usage (manual)

### Extract posts

```bash
# Extract 5 scroll batches of posts (default — good for testing)
uv run python extractor/extract_group.py

# Extract 20 scroll batches
uv run python extractor/extract_group.py --pages 20

# Extract ALL posts (scrolls until no more posts load)
uv run python extractor/extract_group.py --pages 0

# Use a different cookies file
uv run python extractor/extract_group.py --cookies /path/to/cookies.txt

# Debug mode — opens a visible browser window so you can see what's happening
uv run python extractor/extract_group.py --debug
```

Output is saved to `output/group_posts.json`.

### Download images

After extracting posts, download all referenced images locally:

```bash
uv run python extractor/download_images.py
```

Images are saved to `output/images/`.

### Manual image tagging (optional)

If you want to correct or supplement the automatic classification:

1. Run the classifier pipeline to generate initial labels:

```bash
./run.sh classify
```

This writes `output/image_labels.csv` and `output/image_labels.json`.

2. Open `output/image_labels.csv` in a spreadsheet editor (Excel, Numbers, LibreOffice Calc). Edit the `image_type` column with:
   - `noodles`
   - `storefront`
   - `other`

   Set `is_manual` to `true` for any row you manually correct.

3. Save your changes, then re-run the classifier:

```bash
./run.sh classify
```

The classifier automatically:
- **Never overwrites** rows where `is_manual` is `true`.
- **Fine-tunes** a ResNet model on your manual labels (cached — only retrains if the label count changes).
- **Falls back** to zero-shot CLIP (or base ResNet) when no manual labels exist yet.

### Plot on a map

After extracting posts, geocode locations and generate an interactive map:

```bash
uv run python extractor/map_posts.py
```

This will:
1. Extract location info from post text (postal codes, addresses, stall names, check-in locations)
2. Geocode each location using the OneMap API
3. Generate an interactive HTML map at `docs/index.html`

Geocoding results are cached in `output/geocode_cache.json` so subsequent runs are faster.

---

## How it works

### Step 1: Extraction (`extract_group.py`)

Uses [Playwright](https://playwright.dev/) to scrape the public Facebook group in a headless Chromium browser.

1. **Authentication** — loads exported browser cookies (`facebook_cookies.txt`) to access the group as a logged-in user
2. **Scrolling** — auto-scrolls the group feed to load posts (configurable number of scroll batches, or `--pages 0` for all)
3. **Parsing** — extracts structured data from each post:
   - Author name and profile link
   - Post text content
   - Facebook check-in location (if tagged)
   - Image URLs (from Facebook CDN)
   - Reaction counts
   - Comments (author, text, images, timestamp)
   - Post permalink
4. **Output** — saves all posts as JSON to `output/group_posts.json`

### Step 2: Image download (`download_images.py`)

Downloads all referenced images locally before Facebook CDN URLs expire (typically hours to days).

- Reads image URLs from `output/group_posts.json`
- Downloads each image to `output/images/` with deduplication
- Skips already-downloaded images on subsequent runs

### Step 3: Geocoding & mapping (`map_posts.py`)

Transforms raw posts into an interactive map through a multi-stage pipeline:

#### Location extraction
For each post, extracts location candidates from multiple sources:
1. **Facebook check-in** — the `location` field if the author tagged a place
2. **Postal codes** — 6-digit Singapore postal codes found in post text
3. **Known stall aliases** — a curated dictionary mapping colloquial names (e.g. "Kim Keat Hokkien Mee") to geocodable addresses
4. **Street addresses** — regex patterns for Singapore address formats (Block/Blk + street, Lorong patterns)
5. **Singapore abbreviations** — expands common shorthand (AMK → Ang Mo Kio, TPY → Toa Payoh, etc.)

#### Geocoding (two-phase)
Each location candidate is geocoded with caching to avoid redundant API calls:
1. **OneMap API** (primary) — Singapore government geocoder, accurate for local addresses, HDB blocks, and hawker centres
2. **Nominatim/OpenStreetMap** (fallback) — knows POIs, restaurants, and landmarks that OneMap may not index

Results outside Singapore's bounding box (lat 1.15–1.47, lng 103.60–104.05) are rejected.

#### Map generation
1. **Groups** posts by geocoded lat/lng into unique stall locations
2. **Sorts** locations by post count (most discussed first), then alphabetically
3. **Builds** a JSON data payload with metadata and all locations/posts
4. **Injects** the data into `extractor/map_template.html` by replacing placeholders:
   - `__MAP_DATA__` → JSON payload with all locations and posts
   - `__GROUP_URL__` → Facebook group URL for attribution links
5. **Outputs** the final `docs/index.html` — a single HTML file with embedded CSS, JS, and data

### Map features

The generated map (`docs/index.html`) includes:

- 🗺️ **Interactive map** — Leaflet 1.9.4 with OneMap Singapore tiles and MarkerCluster
- 📍 **Custom markers** — Hokkien Mee bowl icon for each stall location
- ⭐ **Sentiment ratings** — star ratings (1-5) based on comment sentiment analysis
- 🔍 **Location search** — filter sidebar by location name
- 📡 **"Near me" geolocation** — uses browser Geolocation API with haversine distance calculation, sorts stalls by proximity
- 🖼️ **Photo thumbnails** — sidebar cards show actual food photos from posts
- 💬 **Rich popups** — click a marker to see all posts for that location with images, reactions, and Facebook links
- 🔗 **Image lightbox** — click any photo to enlarge
- 📊 **Metadata badge** — shows total posts, locations, and average rating with privacy tooltip
- 📱 **Responsive** — works on mobile with collapsible sidebar
- ♿ **Accessibility** — high-contrast mode, keyboard navigation, reduced motion support, ARIA labels

---

## Output format

`output/group_posts.json` contains an array of post objects:

```json
{
  "extracted_at": "2026-02-18T12:00:00+00:00",
  "group_url": "https://www.facebook.com/groups/227074250721100/",
  "total_posts": 42,
  "posts": [
    {
      "post_id": "123456789",
      "author": "Author Name",
      "author_link": "https://www.facebook.com/groups/.../user/123/",
      "timestamp": "4d",
      "extracted_at": "2026-02-18T12:00:00.000Z",
      "text": "Best hokkien mee at ...",
      "location": "Chuan Fried Hokkien Prawn Mee 川炒福建虾面",
      "images": ["https://scontent..."],
      "reactions": "15 reactions; see who reacted to this",
      "comments": [
        {
          "author": "Commenter Name",
          "author_link": "https://www.facebook.com/groups/.../user/456/",
          "text": "I agree!",
          "images": [],
          "timestamp": "4 days ago"
        }
      ],
      "post_link": "https://www.facebook.com/groups/.../posts/123456789/"
    }
  ]
}
```

- **`timestamp`** is Facebook's relative time (e.g. "4d", "6h"). Use **`extracted_at`** on each post (and at the top level) to calculate the actual date.
- **Image URLs expire** after a few hours/days. Run `download_images.py` soon after extraction to save them locally.

---

## GitHub Pages deployment

The map is designed to be hosted on GitHub Pages directly from the `docs/` folder.

### Enable GitHub Pages

1. Go to your repo **Settings → Pages**
2. Under **Source**, select **Deploy from a branch**
3. Set branch to **main** and folder to **/ docs**
4. Click **Save**

The map will be live at `https://<username>.github.io/hokkien-mee/` within a few minutes.

Every time you push an updated `docs/index.html`, the site is automatically redeployed.

---

## Project structure

```
hokkien-mee/
├── README.md
├── pyproject.toml
├── run.sh                  ← run pipeline (extract → images → map)
├── .gitignore
├── facebook_cookies.txt    ← you create this (git-ignored)
├── secrets/
│   └── secrets.py          ← you create this (git-ignored)
├── extractor/
│   ├── extract_group.py    ← extracts posts + comments to JSON
│   ├── download_images.py  ← downloads images locally
│   ├── map_posts.py        ← geocodes locations and builds map
│   └── map_template.html   ← HTML/CSS/JS template for the map
├── docs/
│   └── index.html          ← interactive map (deployed to GitHub Pages)
└── output/                 ← created automatically
    ├── group_posts.json    ← extracted data (version controlled)
    ├── geocode_cache.json  ← cached geocoding results (git-ignored)
    └── images/             ← downloaded images (git-ignored)
```
