# Image Downloading

Saves all photos from extracted posts before their links expire. Facebook photo URLs typically last only hours to days — this step converts them into permanent local copies.

## Why it exists

The extraction step captures URLs pointing to photos on Facebook's servers, but those URLs don't last. Without downloading promptly, the dataset loses its images and the map has nothing to show.

## User stories

- As a **maintainer**, I want photos saved locally so they're still available after Facebook CDN links expire.
- As a **map visitor**, I want to see actual food photos on the map so I can judge a stall before visiting.
- As a **maintainer**, I want the download step to be idempotent so I can re-run it without duplicating work.

## How it works

1. **Load posts** — reads `output/group_posts.json` (supports both envelope format and legacy flat array).
2. **Skip already-downloaded** — checks both `output/images/` and `docs/images/`. If one copy exists but the other is missing, syncs them via a file copy rather than re-downloading.
3. **Download** — fetches each image URL with a 30 s timeout. No Facebook authentication required — images are fetched directly from public CDN URLs.
4. **Mirror** — copies each downloaded file to `docs/images/` so GitHub Pages can serve it.
5. **Report** — prints a summary of downloaded vs. failed images.

Run immediately after `extract_group.py`. It's built into the default pipeline (`./run.sh`) so it runs automatically.

## Reference

**Script:** `extractor/download_images.py`

**Input:** `output/group_posts.json`

**Outputs:**
- `output/images/<post_id>_<index>.jpg` — local copies for processing
- `docs/images/<post_id>_<index>.jpg` — copies served by GitHub Pages

**Timeout:** 30 s per image request.
