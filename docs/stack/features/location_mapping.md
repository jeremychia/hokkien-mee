
# Location Mapping

## Overview
Location mapping connects classified images and posts to real-world locations, enabling powerful geospatial analysis and interactive visualizations.

- **Scripts:** `extractor/map_posts.py`, `extractor/location_overrides.json`, `extractor/map_template.html`
- **Purpose:** Maps classified images and posts to geographic locations.
- **Inputs:**
	- Classified image data
	- Group post data
	- Location overrides
- **Outputs:**
	- Interactive map in `output/hokkien_mee_map.html`

## Product Value
- Transforms raw data into actionable insights by visualizing food trends geographically.
- Supports decision-making for businesses, researchers, and food enthusiasts.
- Enables discovery of hotspots, trends, and outliers in the data.

## How it works
1. Matches posts and images to locations using available data and manual overrides.
2. Generates an interactive HTML map for exploration and sharing.

## User Impact
- Empowers users to explore food trends by location.
- Facilitates research and storytelling with visual data.
- Provides a shareable, interactive resource for the community.
