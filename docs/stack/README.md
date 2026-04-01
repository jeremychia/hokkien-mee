# Project Stack Overview

This documentation describes the architecture, setup, and features of the Hokkien Mee project. Each major feature is documented in a separate file for clarity.

## Structure
- [features/](features/) — Documentation for each major feature
- [setup.md](setup.md) — Environment and setup instructions
- [architecture.md](architecture.md) — High-level system architecture

## Features
- [Group Extraction](features/group_extraction.md) — Scrapes posts and metadata from the Facebook group
- [Image Downloading](features/image_downloading.md) — Downloads images referenced in posts
- [Image Classification](features/image_classification.md) — Classifies images (noodles, storefront, other) using a fine-tuned ResNet model
- [Location Mapping](features/location_mapping.md) — Geocodes posts and renders the interactive map
- [Secrets Management](features/secrets_management.md) — Manages API keys and cookies securely

## Potential Features

See [potential-features.md](potential-features.md) for ideas on future improvements.
