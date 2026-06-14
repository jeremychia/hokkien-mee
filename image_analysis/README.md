# image_analysis

Computer vision pipeline that classifies Hokkien mee images by dish style (wet/dry) and detects visible ingredients. Produces a structured CSV for downstream analysis.

## Pipeline overview

```
Stage 1   Manual labelling in Label Studio
            ↓
Stage 1.5  split_dataset.py  →  data/images|labels|style/train|val/
            ↓
Stage 2    train_detector.py + train_classifier.py  →  runs/
            ↓
Stage 3    analyse.py  →  output/results_<timestamp>.csv
```

## Output schema

| Column | Type | Description |
|---|---|---|
| `image_id` | string | Filename without extension, e.g. `12345_0` |
| `post_id` | string | Derived from `image_id` — joins to post/stall data |
| `source_path` | string | Relative path to image |
| `style` | string | `wet`, `dry`, or `unknown` |
| `style_confidence` | float | Classifier confidence (0–1); filter on this for high-trust results |
| `prawns` | bool | Large whole prawns visible |
| `squid` | bool | Squid or cuttlefish visible |
| `pork_belly` | bool | Sliced pork belly visible |
| `pork_lard` | bool | Crispy white lard bits visible |
| `egg` | bool | Egg (whole, sliced, or broken) visible |
| `bean_sprouts` | bool | Bean sprouts visible |
| `fish_cake` | bool | Fish cake slices visible |
| `sambal` | bool | Chilli sambal on side or on dish |
| `calamansi` | bool | Calamansi or lime wedge visible |
| `chives` | bool | Chinese chives or spring onion visible |
| `notes` | string | `inference_error` or free-text observations |

---

## Setup

```bash
uv sync
```

Label Studio must be started with local file serving enabled so it can load images stored on disk. Without these env vars, image URLs of the form `/data/local-files/?d=output/images/...` will fail to load in the labelling UI:

```bash
LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true \
LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/Users/jeremychia/Documents/Github/hokkien-mee \
label-studio start
```

This opens Label Studio at http://localhost:8080. `DOCUMENT_ROOT` tells Label Studio where to resolve relative paths — it must point to the repo root so that `output/images/<filename>.jpg` resolves correctly.

---

## Stage 1 — Manual labelling

### 1. Generate the noodle image list

Run from the repo root to filter the 1,180 noodle images from `output/image_labels.json`:

```bash
uv run python image_analysis/filter_images.py
# Output: image_analysis/exports/noodle_paths.txt (one absolute path per line)
```

### 2. Set up Label Studio

1. Create a new project: **Object Detection with Bounding Boxes**
2. Restart Label Studio with local file serving enabled:
   ```bash
   LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true \
   LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/Users/jeremychia/Documents/Github/hokkien-mee \
   label-studio start
   ```
3. In **Settings → Cloud Storage → Add Source Storage**, choose **Local files**, set the path to `output/images/`, toggle **Treat every bucket object as a source file** on, click **Add Storage**, then **Sync**

   > **Note on task volume:** Syncing `output/images/` imports all 1,947 images (noodles + storefronts + other). This is the simplest setup. The alternative — symlinking only the 1,180 noodle images into a separate folder — keeps the project tidy but requires extra setup. With the full sync, just label the noodle dishes and skip everything else; Label Studio leaves unlabelled tasks out of the export, so `split_dataset.py` only sees what you actually annotated.

4. Replace the labelling interface XML with:

```xml
<View>
  <Image name="image" value="$image"/>

  <Choices name="style" toName="image" choice="single" showInLine="true">
    <Choice value="wet"/>
    <Choice value="dry"/>
  </Choices>

  <RectangleLabels name="label" toName="image">
    <Label value="prawns"/>
    <Label value="squid"/>
    <Label value="pork_belly"/>
    <Label value="pork_lard"/>
    <Label value="egg"/>
    <Label value="fish_cake"/>
    <Label value="sambal"/>
    <Label value="calamansi"/>
    <Label value="chives"/>
  </RectangleLabels>
</View>
```

### 3. Labelling guidelines

**Style (image-level choice — always fill this in):**
- `wet` — noodles appear glossy/saucy, dark sauce pooling is visible
- `dry` — noodles are drier, typically served with sambal on the side

**Ingredients (draw bounding boxes):**

| Label | What to box | Notes |
|---|---|---|
| `prawns` | Whole prawn including head/tail | Very distinct — high priority |
| `squid` | Rings or tentacle clusters | Can resemble pale noodle sections |
| `pork_belly` | Sliced pieces — look for layered fat/meat | May be partially buried |
| `pork_lard` | Distinct clusters of crispy white/golden bits only | Easily confused with `fried_garlic` |
| `egg` | Whole, halved, or clearly broken mass | Skip ambiguous scrambled fragments |
| `bean_sprouts` | Visible white stalks — box the densest cluster | Often scattered |
| `fish_cake` | Pale slices with uniform texture | |
| `sambal` | Chilli paste portion, served separately or on dish | |
| `calamansi` | The whole wedge or half fruit | |
| `chives` | Visible green stalks | Low frequency — skip if ambiguous |

**Keyboard shortcuts:**
- **Cmd+Enter** — submit annotation and move to next task
- Number keys (shown next to each label) — activate a label quickly before drawing a box

**Sparse class strategy:** If a class appears in fewer than ~10% of your images, skip labelling it for the first training run. Candidates to defer: `chives`, `fish_cake`. Focus on `prawns`, `squid`, `sambal`, `calamansi`, `pork_belly`, `dark_sauce`.

### 4. Zero-shot pre-labelling (optional but recommended)

Before opening Label Studio, run the pre-labeller to get draft labels on 120 images automatically using Claude vision. Tasks will open in Label Studio with bounding boxes and style choices already filled in — your job is just to review and correct, not label from scratch.

```bash
uv run python image_analysis/prelabel.py
# Output: image_analysis/exports/prelabels.json
```

Then in Label Studio: **Project → Import → upload `prelabels.json`**

Options:
```
--limit N    Number of images to pre-label (default 120)
--delay N    Seconds between API calls     (default 0.5)
--output     Output path for the JSON file
```

Cost at 120 images with `claude-sonnet-4-6`: approximately $3–6 USD.

### 5. Recommended labelling volume

**Label 300+ images** for a useful detector. At 120–150 images the model trains but mAP50 stays around 0.13–0.14 — too low for reliable inference. 300 images should get the common classes (prawns, calamansi, sambal, squid) above mAP50 0.5. Rare classes like `egg` will need more examples still, but keeping them in is intentional — the goal is to detect rare ingredients too, not just common ones.

---

## Stage 1.5 — Split dataset

After labelling, export from Label Studio **once**:

**Export → JSON** → save as `image_analysis/exports/raw/annotations.json`

> Filter to annotated tasks first: use **Filter → Annotation → is completed** before exporting so only labelled images are included.

Then run:

```bash
uv run python -m image_analysis.split_dataset
```

Options:
```
--labels-json    Label Studio JSON export  (default: image_analysis/exports/raw/annotations.json)
--dest           Output data directory     (default: image_analysis/data/)
--repo-root      Repo root for resolving image paths (default: .)
--val-ratio      Validation fraction       (default: 0.2)
--seed           Random seed               (default: 42)
```

---

## Stage 2 — Train models

```bash
uv run python image_analysis/train_detector.py
uv run python image_analysis/train_classifier.py
```

Review before proceeding:
- `image_analysis/runs/detect/ingredients_v1/results.png`
- `image_analysis/runs/detect/ingredients_v1/confusion_matrix.png`
- `image_analysis/runs/classify/style_v1/results.png`

**Model size guide:**

| Model flag | Speed | Accuracy | Use when |
|---|---|---|---|
| `yolov8n.pt` | Fastest | Lower | < 200 images, CPU only |
| `yolov8s.pt` | Fast | Moderate | 200–500 images |
| `yolov8m.pt` | Moderate | Good | 500+ images, GPU available |

Pass `--model yolov8s.pt` once you have more labels.

---

## Stage 3 — Inference

```bash
# Dry run — lists images without loading models
uv run python image_analysis/analyse.py --dry-run

# Full run
uv run python image_analysis/analyse.py
```

Output is written to `output/results_<timestamp>.csv`. Re-running never overwrites an existing file.

Options:
```
--labels               image_labels.json path        (default: output/image_labels.json)
--detector-weights     Trained detector weights       (default: ...ingredients_v1/weights/best.pt)
--classifier-weights   Trained classifier weights     (default: ...style_v1/weights/best.pt)
--output               Base CSV output path           (default: output/results.csv)
--conf                 Detection confidence threshold (default: 0.35)
--style-conf           Min classifier confidence      (default: 0.55)
--no-filter            Process all image types        (default: noodles only)
```

---

## Iterating on the model

**If mAP50 < 0.5 overall:**
- Label more images for the weakest classes
- Lower `--conf` in `analyse.py`
- Upgrade from `yolov8n` to `yolov8s`

**If a specific class is consistently missed (e.g. `pork_lard`):**
- Accept it may be too ambiguous at this dataset size
- Remove it from `ingredients.yaml`, retrain, and re-add once you have ≥ 15 examples

**If false positives are high:**
- Raise `--conf` in `analyse.py`
- Review and correct labels in Label Studio, then retrain
