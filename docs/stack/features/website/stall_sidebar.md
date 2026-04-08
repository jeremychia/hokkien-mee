# Stall Sidebar

Lists every stall in a scrollable panel alongside the map. You can search by name or area, and sort by how discussed, highly rated, or well-liked each stall is.

## Why it exists

The map is good for spatial exploration but not for scanning or comparing stalls. The sidebar gives you a ranked list you can search through without clicking individual markers.

## User stories

- As a **food hunter**, I want to see all stalls in a list so I can scan them without clicking every marker.
- As a **local**, I want to search by neighbourhood so I can quickly find stalls near a specific area.
- As a **researcher**, I want to sort by most discussed so I can see which stalls the community talks about most.
- As a **visitor**, I want to sort by highest rated so I can go straight to the best-reviewed options.
- As a **food hunter**, I want each card to show a food photo so I can get a visual impression before clicking.

## How it works

Each stall appears as a card with a thumbnail, address, post count, reaction count, and star rating. Clicking a card zooms the map to that stall and opens its popup. The search bar filters cards in real time as you type (150 ms debounce). Sorting reorders the list instantly.

When "Near me" is active, distance overrides all sort options.

**Sort options:**
- **Most discussed** — by post count; tiebreak alphabetical
- **Highest rated** — by sentiment score; unrated stalls go last; tiebreak by post count
- **Most liked** — by total reaction count; tiebreak alphabetical

## Reference

**Search:** `#searchInput`, debounce 150 ms, matches `card.dataset.search` (lowercased address).

**Card data attributes:** `data-idx`, `data-search`, `data-posts`, `data-rating` (float, `-1` if unrated), `data-reactions`

**Thumbnail priority:** first image of type `noodles` → `storefront` → any. Falls back to inline SVG.

**Active state:** `setActiveLocation(idx)` adds `.active` class, sets `aria-selected="true"`, calls `scrollIntoView()` (smooth, or auto if `prefers-reduced-motion`).

**Keyboard:** `Enter`/`Space` opens popup; `ArrowUp`/`ArrowDown` moves focus between cards.
