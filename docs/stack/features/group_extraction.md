# Group Extraction

Automatically collects posts from the Hokkien Mee Facebook group — including text, photos, reactions, comments, and location tags — and saves them as structured data for everything else in the pipeline to use.

## Why it exists

The Facebook group is where the community shares their finds, but the data is locked inside Facebook's UI. This feature liberates it: turning an unstructured social feed into a dataset that can be mapped, classified, and analysed.

## User stories

- As a **maintainer**, I want to collect all posts from the group automatically so I don't have to copy data manually.
- As a **maintainer**, I want full comment threads captured so the dataset reflects the whole conversation, not just the original post.
- As a **maintainer**, I want to control how much of the feed to collect so I can do quick test runs without waiting for a full extraction.
- As a **maintainer**, I want to backfill older posts so gaps in the dataset can be filled without re-collecting everything.

## How it works

1. **Authenticate** — loads `facebook_cookies.txt` into a headless Chromium browser (via Playwright) to access the group as a logged-in user.
2. **Navigate** — opens the group feed in chronological order (`?sorting_setting=CHRONOLOGICAL`).
3. **Scroll** — auto-scrolls in batches of 3 scrolls each, with randomised pauses (3–6 s) to avoid rate-limiting. Waits for Facebook's loading indicators to clear before continuing.
4. **Parse feed** — after each batch, extracts author, post text, check-in location, image URLs, reaction count, and permalink from every visible post.
5. **Fetch comments** — opens each post's permalink in a new tab to collect all comments (the feed only shows 1–2 inline). Expands "View more comments / replies" until all are loaded.
6. **Deduplicate & save** — merges newly extracted posts with any existing `output/group_posts.json`, deduplicates by post ID, and writes the result.

## Reference

**Script:** `extractor/extract_group.py`

**Flags:**
- `--pages N` — scroll batches to load (default: 5; `0` = unlimited)
- `--cookies PATH` — path to a custom cookies file (default: `facebook_cookies.txt`)
- `--debug` — run browser in headed (visible) mode
- `--backfill` — keep scrolling past already-extracted posts to fetch older ones

**Output:** `output/group_posts.json`

**Scroll constants:** `SCROLLS_PER_PAGE = 3`, pause `3–6 s` per scroll, up to 15 s wait near the bottom for Facebook to load more content.
