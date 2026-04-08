# Image Classification

Automatically labels every downloaded image as noodles, storefront, or other — so the map shows relevant food photos rather than random pictures from posts.

## Why it exists

Posts contain all kinds of images: the noodles themselves, the stall front, menus, receipts, selfies. Without classification, the map would show whatever image happened to be attached to a post. Classification ensures photo thumbnails show the most useful images.

## User stories

- As a **map visitor**, I want to see food photos on stall cards so I know what the dish looks like before visiting.
- As a **maintainer**, I want irrelevant images filtered out automatically so the map isn't cluttered with receipts and selfies.
- As a **maintainer**, I want to correct wrong labels in a browser UI so I don't have to edit raw files.
- As a **maintainer**, I want my corrections to improve future classification so the model gets better with minimal ongoing effort.

## How it works

The classifier picks the best available model automatically:

| Condition | Model used |
|---|---|
| Manual labels exist + cache valid (same label count) | Load cached fine-tuned ResNet |
| Manual labels exist + cache stale or missing | Fine-tune ResNet, save new cache |
| No manual labels | Zero-shot CLIP, or base ResNet as fallback |

**Pipeline steps:**
1. **Load posts** — reads `group_posts.json` and collects all image paths from `output/images/`.
2. **Load manual labels** — reads rows from the CSV where `is_manual` is `true`. These are never overwritten.
3. **Select & prepare model** — applies the logic above. If fine-tuning, trains the final classification layer of ResNet50. With ≥ 10 manual labels, runs k-fold cross-validation (up to 5 folds) first.
4. **Classify** — runs each unclassified image through the model. Predictions below `--confidence-threshold` fall back to `other`.
5. **Merge & save** — merges new predictions with existing manual labels.
6. **Report** — writes a markdown summary with per-class counts and model info.

To correct labels: run the classifier first to generate initial labels, then open the labeling tool (`python label_server.py`) in your browser. Mark corrected rows as manual — they persist across all future runs.

## Reference

**Script:** `extractor/classify_images.py`

**Flags:**
- `--input PATH` — path to `group_posts.json` (default: `output/group_posts.json`)
- `--csv PATH` — path to labels CSV for manual corrections (default: `output/image_labels.csv`)
- `--output PATH` — output JSON path (default: `output/image_labels.json`)
- `--report PATH` — output report path (default: `output/image_classification_report.md`)
- `--preview N` — print top N rows after classification (default: 10)
- `--confidence-threshold F` — minimum confidence to accept a prediction (default: 0.5)
- `--skip-model` — skip model-based classification, use heuristic only

**Outputs:**
- `output/image_labels.json` — labels keyed by image path
- `output/image_labels.csv` — same, in CSV form
- `output/image_classification_report.md` — per-class counts and model performance
- `output/finetuned_resnet.pth` — cached model weights
- `output/finetuned_resnet_info.json` — cache metadata (label count, used to detect when retraining is needed)
