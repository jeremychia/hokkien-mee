
# Group Extraction

## Overview
Group extraction is the process of collecting posts and metadata from Facebook groups. This feature is essential for understanding the context of each image and for mapping posts to locations and users.

- **Script:** `extractor/extract_group.py`
- **Purpose:** Extracts posts from Facebook groups for further analysis.
- **Inputs:**
	- Facebook cookies (`facebook_cookies.txt`)
- **Outputs:**
	- Group post data in `output/group_posts.json`

## Product Value
- Enables large-scale, automated data collection from social media communities.
- Captures rich context (text, timestamps, user info) for each post.
- Lays the foundation for analytics, mapping, and trend analysis.

## How it works
1. Authenticates with Facebook using provided cookies.
2. Scrapes posts from specified groups, including text, images, and metadata.
3. Saves post data in a structured format for downstream tasks.

## User Impact
- Provides a comprehensive dataset for research and product features.
- Reduces manual effort in data collection.
- Supports new features such as trend analysis, user engagement tracking, and more.
