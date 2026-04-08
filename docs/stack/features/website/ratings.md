# Ratings

Shows a star rating (1–5) for each stall, derived automatically from the language people used in their posts and comments — no manual scoring required.

## Why it exists

Reaction counts tell you a post was popular, but not whether the verdict was positive or negative. Ratings surface the community's actual opinion: a stall that gets enthusiastic comments consistently scores higher than one that gets lukewarm mentions.

## User stories

- As a **food hunter**, I want to see a star rating for each stall so I can quickly identify community favourites.
- As a **visitor**, I want to know how many posts the rating is based on so I can judge how reliable it is.
- As a **researcher**, I want to understand how ratings are calculated so I can interpret them correctly.
- As a **map visitor**, I want unrated stalls to be clearly distinguished so I don't mistake "no rating" for a bad score.

## How it works

Every post and comment for a stall is scanned for sentiment signals — positive words like "shiok", "best", "worth the queue" and negative ones like "bland", "disappointing", "avoid". The ratio of positive to negative signals maps to a 1–5 star scale.

A stall needs at least 2 posts or comments with clear signals before it gets a rating. Stalls with too little data show no stars. Tap the ⓘ icon next to a rating to read a full explanation of the methodology.

Ratings are computed by `map_posts.py` at map generation time and embedded in the data payload — they are not recalculated in the browser.

## Reference

**Data shape (`loc.sentiment`):**
```json
{
  "score": 4.2,         // float 1.0–5.0, or null if unrated
  "positive": 18,       // positive signal count
  "negative": 3,        // negative signal count
  "rated_comments": 12  // comments with at least one signal
}
```

**Star rendering (`starsHtml(score)`):** `Math.floor(score)` full stars (`★`), half star (`½`) if decimal ≥ 0.5, remainder empty (`☆`) to 5 total. Example: `3.7` → `★★★½☆`.

**Rendering locations:**
- Sidebar card: `.loc-stars` — stars only, colour `#F39C12`
- Popup header: `.popup-rating` — `.stars` + `.score` (numeric) + `.basis` (comment count)

**Sort:** `card.dataset.rating` stores the float; unrated = `-1` so they sort last under "Highest rated".

**Methodology tooltip:** `#ratingInfoBtn` toggles `.show` on `.rating-tooltip`. Global click listener closes it when clicking outside.
