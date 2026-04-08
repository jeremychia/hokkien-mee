# Sharing & Navigation

Lets you share a specific stall with someone else, get directions to it, or suggest a correction if something looks wrong.

## Why it exists

Finding a great stall is one thing — being able to send it to a friend, open it in Google Maps, or flag an error closes the loop between discovery and doing something about it.

## User stories

- As a **food hunter**, I want to copy a link to a specific stall so I can share it with friends.
- As a **local**, I want to open directions to a stall in Google Maps so I can navigate there directly.
- As a **contributor**, I want to suggest a correction to a stall's location so the map stays accurate over time.
- As a **food hunter**, I want a shared link to open the map already focused on the right stall so my friends don't have to search for it.

## How it works

**Share** — copies a deep link to your clipboard. The link opens the map with that stall's popup already open, zoomed in. Works in any browser that supports the Clipboard API.

**Directions** — opens Google Maps in a new tab with the stall set as the destination. Works on desktop and mobile.

**Suggest edit** — opens a Google Form pre-filled with the stall's address and ID. Used to flag location errors or suggest corrections without editing any files directly.

## Reference

**Share:** `copyDeepLink(url)` calls `navigator.clipboard.writeText(url)`. Feedback: `alert('Link copied to clipboard!')`. No fallback if Clipboard API is unavailable.

**Deep link format:** `{origin}{pathname}?id={loc.id}` — `loc.id` is an 8-char SHA256 hash of the stall address, stable across map regenerations.

**Deep link handling on load:** 500 ms delay, then `cluster.zoomToShowLayer(marker, callback)` → open popup → set active card → scroll into view.

**Google Maps:** `https://www.google.com/maps/dir/?api=1&destination={lat},{lng}` — `<a target="_blank" rel="noopener">`.

**Suggest edit form:** ID `1FAIpQLSeIuOm0serxmrkzNygEaXiIDy3plD4DBIg_AcJBsprd97o0Uw`, pre-filled with `entry.1007330317` (address) and `entry.1388685291` (stall ID) via `encodeURIComponent`.

**Location ID display:** `<span class="popup-id">ID: {loc.id}</span>` with `user-select: all` — click to select the full ID.
