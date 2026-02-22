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

## Usage

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

### Plot on a map

After extracting posts, geocode locations and generate an interactive map:

```bash
uv run python extractor/map_posts.py
```

This will:
1. Extract location info from post text (postal codes, addresses, stall names, check-in locations)
2. Geocode each location using the OneMap API
3. Generate an interactive HTML map at `output/hokkien_mee_map.html`

Geocoding results are cached in `output/geocode_cache.json` so subsequent runs are faster.

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

## Project structure

```
hokkien-mee/
├── README.md
├── pyproject.toml
├── .gitignore
├── facebook_cookies.txt    ← you create this (git-ignored)
├── secrets/
│   └── secrets.py          ← you create this (git-ignored)
├── extractor/
│   ├── extract_group.py    ← extracts posts + comments to JSON
│   ├── download_images.py  ← downloads images locally
│   └── map_posts.py        ← geocodes locations and builds HTML map
└── output/                 ← created automatically
    ├── group_posts.json    ← extracted data (version controlled)
    ├── geocode_cache.json  ← cached geocoding results (git-ignored)
    ├── hokkien_mee_map.html ← interactive map (version controlled)
    └── images/             ← downloaded images (git-ignored)
```
