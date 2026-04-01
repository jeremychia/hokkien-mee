
# Location Mapping

## Overview
Location mapping connects classified images and posts to real-world locations, enabling powerful geospatial analysis and interactive visualizations.

- **Scripts:** `extractor/map_posts.py`, `extractor/location_overrides.json`, `extractor/map_template.html`
- **Purpose:** Maps classified images and posts to geographic locations.
- **Inputs:**
	- Classified image data
	- Group post data
	- Location overrides (`extractor/location_overrides.json`)
- **Outputs:**
	- Interactive map at `docs/index.html` (published via GitHub Pages)
	- Geocoding cache at `output/geocode_cache.json`

## Product Value
- Transforms raw data into actionable insights by visualizing food trends geographically.
- Supports decision-making for businesses, researchers, and food enthusiasts.
- Enables discovery of hotspots, trends, and outliers in the data.

## How it works
1. Extracts location information from post text and metadata, using a curated alias dictionary and `location_overrides.json` for corrections.
2. Geocodes each location via the OneMap API (with Nominatim/OpenStreetMap fallback), caching results to avoid redundant requests.
3. Groups posts by location and computes a sentiment score for each stall based on post and comment language.
4. Renders an interactive Leaflet map from `map_template.html`, showing a marker per stall with a popup containing posts, images, ratings, directions, and sharing links.
5. Each image in the lightbox displays the contributor (author), the post ID, and a direct link to the original Facebook post for attribution.

## Image Attribution
When a user clicks on an image in the map popup, the lightbox shows:
- **By:** the name of the person who posted the image
- **ID:** the internal post ID
- **View post ↗** — a link that opens the original Facebook post in a new tab

## Location Overrides
Stall addresses that geocoders cannot resolve are maintained in `extractor/location_overrides.json` and `extractor/map_posts.py` (`LOCATION_ALIASES`). This includes:
- Known stall → address mappings (e.g. `"chuan hokkien mee"` → `"80 Circuit Road, #02-05, Singapore 370080"`)
- Merges to consolidate duplicate location names
- Renames and excludes for data quality

## User Impact
- Empowers users to explore food trends by location.
- Facilitates research and storytelling with visual data.
- Provides a shareable, interactive resource for the community.
