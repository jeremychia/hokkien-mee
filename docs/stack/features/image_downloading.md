
# Image Downloading

## Overview
The image downloading feature is responsible for collecting visual data from Facebook group posts. This is the entry point for building the dataset and is foundational for all subsequent analysis.

- **Script:** `extractor/download_images.py`
- **Purpose:** Downloads images from Facebook group posts.
- **Inputs:**
	- Facebook cookies (`facebook_cookies.txt`)
	- Group post data
- **Outputs:**
	- Images saved to `output/images/`

## Product Value
- Automates the collection of user-generated content from social media.
- Ensures a steady pipeline of new data for analysis and model training.
- Handles authentication and error recovery for robust scraping.

## How it works
1. Authenticates using Facebook cookies to access group content.
2. Iterates through group posts, downloading referenced images.
3. Stores images in a structured directory for downstream processing.

## User Impact
- Provides a reliable, automated way to gather large volumes of images.
- Reduces manual scraping and risk of data loss.
- Ensures data freshness for analytics and model retraining.
