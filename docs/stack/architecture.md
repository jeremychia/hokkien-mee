# System Architecture

The project is organized into several components:

- **extractor/**: Contains scripts for downloading images, extracting group posts, classifying images, and mapping locations.
- **output/**: Stores generated data, model files, and reports.
- **docs/**: Documentation and HTML files for visualization.
- **secrets/**: Stores sensitive information (not tracked in version control).

## Data Flow
1. **Data Extraction**: Download images and extract posts from Facebook groups.
2. **Image Classification**: Classify images using a fine-tuned ResNet model.
3. **Location Mapping**: Map classified images and posts to locations.
4. **Visualization**: Generate HTML reports and maps for analysis.

Each feature is described in detail in the [features](features/) directory.
