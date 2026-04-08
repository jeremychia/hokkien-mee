# Stall Popup

Opens a panel with everything the community has posted about a stall — photos organised by type, the original posts with full text and reactions, and links back to Facebook.

## Why it exists

A map marker alone doesn't tell you much. The popup is where you find out whether a stall is worth visiting: what the food looks like, what people said, and how many people agreed.

## User stories

- As a **food hunter**, I want to see food photos for a stall so I can judge whether it looks good before going.
- As a **visitor**, I want to read what people wrote about a stall so I can set expectations before visiting.
- As a **researcher**, I want to see individual posts with reaction counts so I can identify the most influential opinions.
- As a **food hunter**, I want to click a photo to see it full size so I can look at it properly.
- As a **contributor**, I want a link to the original Facebook post so I can read the full thread or comments.

## How it works

The popup has two tabs:

**Photos** (shown when images exist) — photos grouped by type: noodles, storefront, or other. If a stall has images of multiple types, tab buttons appear with counts. Click any photo to open a full-size lightbox with previous/next navigation. Each photo credits the person who posted it.

**Posts** (always present) — every post mentioning the stall, with author, text, images, and reaction count. Each post links back to Facebook.

In the lightbox, navigate with arrow buttons, keyboard arrows, or swipe on mobile. Press Escape to close.

## Reference

**Function:** `buildPopupHtml(loc)`

**Default tab:** Photos if images exist, Posts otherwise. Within Photos: `noodles` → `storefront` → `other`.

**Image tab rendering (`buildImageTabsHtml`):**
- Single category: grid without tab bar
- Multiple categories: tab buttons with count badges; `switchImgTab(btn)` toggles `.active` / `.hidden`
- Grid: `repeat(auto-fit, minmax(76px, 1fr))`

**Image data attributes:** `data-photo-id`, `data-author`, `data-post-link`, `data-post-id`

**Image error handling:** `handleImgError(this)` tries `data-fallback` src; hides element if that also fails.

**Lightbox:** `openLightboxFromImg(img)` collects all images from `.popup-wrap`. Touch: 45 px minimum horizontal swipe, 1.2× horizontal-to-vertical ratio. Keyboard: `ArrowLeft`/`ArrowRight`, `Escape`.

**Post text:** truncated to 200 characters.

**Popup max height:** `72vh`, scrollable.
