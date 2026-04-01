
# Image Classification

## Overview
The image classification feature enables automated identification of food items in images collected from Facebook group posts. This is crucial for building a structured dataset and powering downstream analytics and mapping.

- **Script:** `extractor/classify_images.py`
- **Purpose:** Classifies downloaded images using a fine-tuned ResNet model.
- **Inputs:**
	- Images from `output/images/`
	- Model weights from `output/finetuned_resnet.pth`
- **Outputs:**
	- Classification results in `output/image_labels.json` and `output/image_labels.csv`
	- Evaluation report in `output/image_classification_report.md`

## Product Value
- Automates the labor-intensive process of labeling food images.
- Ensures consistent, scalable, and repeatable classification.
- Enables rapid iteration and retraining as new data is collected.

## How it works
1. Loads the fine-tuned ResNet model, optimized for food image recognition.
2. Processes each image, predicting the most likely food label.
3. Aggregates results and generates a report for model performance.

## User Impact
- Reduces manual effort for data labeling.
- Improves data quality for analytics and mapping.
- Supports continuous improvement as more images are classified and the model is retrained.
