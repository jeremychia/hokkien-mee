# Hokkien Mee — Image Analysis Pipeline
**Claude Code Handoff · Data Science · YOLOv8 · Manual Labelling**

---

## 1. Objective

Build a computer vision pipeline that ingests images of Hokkien mee and produces a structured per-image dataset indicating style (wet/dry) and visible ingredients. The approach prioritises **manual labelling + YOLOv8 fine-tuning** over LLM inference. LLMs are used only as a last resort (see Section 7).

---

## 2. Output Schema

One row per image. All ingredient columns are boolean.

| Column | Type | Description |
|---|---|---|
| `image_id` | string | Filename without extension (e.g. `img_001`) |
| `source_path` | string | Relative path to the source image |
| `style` | string | `wet`, `dry`, `conflict`, or `unknown` |
| `prawns` | bool | Large whole prawns visible |
| `squid` | bool | Squid or cuttlefish visible |
| `pork_belly` | bool | Sliced pork belly visible |
| `pork_lard` | bool | Crispy white lard bits visible |
| `egg` | bool | Egg (whole, sliced, or broken) visible |
| `bean_sprouts` | bool | Bean sprouts visible |
| `fish_cake` | bool | Fish cake slices visible |
| `sambal` | bool | Chilli sambal on the side or on dish |
| `calamansi` | bool | Calamansi or lime wedge visible |
| `chives` | bool | Chinese chives or spring onion visible |
| `notes` | string | Free-text observations; `parse_error` or `style_conflict` flags written here |

---

## 3. Pipeline Overview

```
images/
  └─► [STAGE 1] Manual labelling (Label Studio)
        └─► Label Studio export (flat zip)
              └─► [STAGE 1.5] split_dataset.py  ← automated train/val split
                    └─► data/images/train|val + data/labels/train|val
                          └─► [STAGE 2] YOLOv8 fine-tuning  ← two-model approach
                          │     ├── style_classifier (wet/dry)
                          │     └── ingredient_detector (YOLO)
                                      └─► runs/
                                            └─► [STAGE 3] Inference + export
                                                  └─► output/results_<timestamp>.csv
```

You are involved in **Stage 1** (manual labelling) before any training begins. Stages 1.5, 2, and 3 are automated.

---

## 3.5 Key Concepts for Beginners

This section explains the data science ideas behind the pipeline. If you are already familiar with computer vision, skip ahead.

### What is a model?

A model is a mathematical function that takes an image as input and produces a prediction as output. Before it can make useful predictions, the model must be **trained** — it looks at thousands of examples where the correct answer is already known (your labelled images) and gradually adjusts its internal numbers until its predictions match those answers.

Think of it like teaching a friend to identify Hokkien mee ingredients by showing them hundreds of photos and saying "yes, that white blob is pork lard" or "no, that's fried garlic" until they develop an eye for it.

### What is fine-tuning?

Training a model from scratch requires millions of images and significant computing time. Instead, we start from a **pre-trained model** (YOLOv8) that has already learned to recognise general shapes, edges, textures, and objects from a huge dataset. We then **fine-tune** it on our small domain-specific dataset (Hokkien mee images), teaching it just the new vocabulary it needs.

Fine-tuning works because the low-level visual skills (detecting edges, colours, shapes) transfer across domains. Only the final layers need significant adjustment to learn "what is a prawn" versus "what is squid".

### What is the train/val split?

When training, the model sees labelled examples and learns from them. The risk is **overfitting** — the model memorises the specific training images rather than learning general rules, so it performs well on training data but fails on new images.

To detect overfitting, we hold back a portion of labelled images (the **validation set**) that the model never trains on. After each training epoch, we check how well the model does on validation images. If training accuracy keeps improving but validation accuracy plateaus or drops, the model is overfitting.

A 70/30 train/val split (the default in `split_dataset.py`) means 70% of images are used for learning, 30% for evaluation. With 100 images, that is 70 training and 30 validation images — tight, but workable.

### What is a bounding box?

A bounding box is a rectangle drawn around an object in an image, defined by four numbers: the x and y coordinates of its centre, its width, and its height (all as fractions of image size, between 0 and 1). Label Studio produces these coordinates when you draw boxes around ingredients.

YOLO learns to predict these boxes — both their location and the class label (e.g. "prawn") — for every object visible in a new image.

### What is a confidence threshold?

The model does not simply say "prawn: yes or no". It outputs a confidence score between 0 and 1 — how sure it is that a detection is correct. A score of 0.9 means it is very confident; 0.2 means it barely sees anything.

The **confidence threshold** (`CONF_THRESHOLD = 0.35` in `analyse.py`) is the cut-off you choose: detections below this score are discarded. Setting it lower catches more true positives but also more false positives. Setting it higher is more precise but misses uncertain detections. You tune this after reviewing the confusion matrix.

### What is mAP?

**mAP (mean Average Precision)** is the standard metric for object detection quality. Here is what the terms mean:

- **Precision**: of all the times the model said "prawn", how often was it actually a prawn?
- **Recall**: of all the prawns in the images, how many did the model find?
- **Average Precision (AP)**: a single number that summarises the precision/recall trade-off for one class across all confidence thresholds.
- **mAP**: the average of AP across all classes (prawns, squid, pork_belly, etc.).

**mAP50** specifically measures performance when a detection is counted as correct only if its bounding box overlaps the true box by at least 50% (IoU ≥ 0.5). An mAP50 above 0.5 is a reasonable starting target; above 0.7 is good.

### What is IoU?

**IoU (Intersection over Union)** measures how well a predicted bounding box matches the labelled box. It is the area of overlap divided by the total area covered by both boxes. A perfect prediction has IoU = 1.0; no overlap at all is 0.0. YOLO uses IoU internally during training to measure how accurate its box predictions are.

### Why two separate models?

We could theoretically build one model to do everything. But wet/dry style is an **image-level property** (it describes the whole dish) while ingredient detection is an **object-level property** (it describes specific regions of the image).

Mixing them forces YOLO to predict style from bounding boxes — which creates the "noodle overlap" problem: you would need to draw a box around the entire noodle mass, which would envelop every ingredient and confuse the loss function during training. Splitting into a classifier (style) and a detector (ingredients) avoids this entirely.

### What happens during a training epoch?

One **epoch** is one complete pass through all training images. During each epoch:

1. The model sees each training image and makes predictions.
2. Its predictions are compared to your labels using a **loss function** — a score that measures how wrong the model is.
3. The model's internal numbers (weights) are nudged slightly in the direction that reduces the loss, using an algorithm called gradient descent.

After many epochs, the weights settle at values that produce accurate predictions. The training scripts use 50 epochs for the detector and 30 for the classifier — reasonable starting points for a small dataset.

---

## 4. Stage 1 — Manual Labelling

### 4.1 Tooling

Use **Label Studio** (open source, runs locally):

```bash
pip install label-studio
label-studio start
```

Opens at `http://localhost:8080`.

### 4.2 Label Taxonomy

**Critical architecture decision:** wet/dry style is handled as an **image-level classification** task, not a bounding box. This avoids the noodle-overlap problem where a giant noodle-mass box envelops every other ingredient, confusing the YOLO loss function.

Label Studio setup:
1. Create a new project: *Object Detection with Bounding Boxes*
2. Import your images from `images/`
3. Add a **Choice** tag for style (image-level):

```xml
<Choices name="style" toName="image" choice="single">
  <Choice value="wet"/>
  <Choice value="dry"/>
</Choices>
```

4. Add the following **bounding box** labels (ingredient detection only):

```
prawns
squid
pork_belly
pork_lard
egg
bean_sprouts
fish_cake
sambal
calamansi
chives
```

> `wet_noodles` and `dry_noodles` are **not** bounding box classes. Style is the image-level choice above.

### 4.3 Labelling Guidelines

| Ingredient | What to box | Known ambiguity |
|---|---|---|
| `prawns` | Whole prawn including head/tail if visible | Very distinct — high priority |
| `squid` | Rings or tentacle clusters | Can resemble pale noodle sections |
| `pork_belly` | Sliced pieces — look for layered fat/meat | May be partially buried |
| `pork_lard` | Distinct clusters of crispy white/golden bits only — skip individual specks | Easily confused with fried garlic or egg fragments |
| `egg` | Whole, halved, or clearly broken mass | Scrambled egg fragments are low-confidence; skip if ambiguous |
| `bean_sprouts` | Visible white stalks | Often scattered — box the densest cluster |
| `sambal` | Chilli paste portion, whether served separately or on dish | |
| `calamansi` | The whole wedge or half fruit | |
| `chives` | Visible green stalks | Low frequency — see note below |

**Sparse class strategy:** If a class appears in fewer than ~10% of your images, skip labelling it for the first training run. It won't learn meaningfully at 100 images. Candidates to defer: `chives`, `fish_cake`. Focus labelling energy on `prawns`, `squid`, `sambal`, `calamansi`, `pork_belly`.

> **Why does class frequency matter?** Neural networks learn by example. If the model sees only 5 images with chives in 100 total, it has almost no signal to learn from — the loss contributed by that class is swamped by the other 95 images. The model will likely learn to never predict chives, because being wrong on 5 images and right on 95 is a better strategy for minimising total loss. More examples per class = better learning.

### 4.4 Export

Export from Label Studio:

- Export → `YOLO with images`
- This produces a **flat zip** — images and label files are not pre-split into train/val folders
- Unzip into `exports/raw/`

Do **not** manually reorganise the export. Run `split_dataset.py` instead (Stage 1.5).

**Minimum recommended dataset size before training:** 80–100 labelled images.

> **Why 80–100?** Below this, the validation set is too small to give reliable accuracy estimates (with 30 images in val, a single misclassified image shifts accuracy by ~3%). It is also too small for the model to learn reliable features — you end up tuning to noise rather than signal. More is always better; 200+ images per class is the gold standard, but 80–100 total is a viable starting point for common classes like prawns.

---

## 5. Stage 1.5 — Automated Train/Val Split

Create `split_dataset.py`. Run this immediately after unzipping the Label Studio export.

```python
import argparse
import random
import shutil
from pathlib import Path


def split(src: Path, dest: Path, val_ratio: float = 0.3, seed: int = 42):
    images = sorted((src / "images").glob("*.*"))
    random.seed(seed)
    random.shuffle(images)

    n_val = int(len(images) * val_ratio)
    splits = {"val": images[:n_val], "train": images[n_val:]}

    for split_name, split_images in splits.items():
        (dest / "images" / split_name).mkdir(parents=True, exist_ok=True)
        (dest / "labels" / split_name).mkdir(parents=True, exist_ok=True)

        for img_path in split_images:
            label_path = src / "labels" / img_path.with_suffix(".txt").name
            shutil.copy(img_path, dest / "images" / split_name / img_path.name)
            if label_path.exists():
                shutil.copy(label_path, dest / "labels" / split_name / label_path.name)
            else:
                # Create empty label file for images with no detections
                (dest / "labels" / split_name / img_path.with_suffix(".txt").name).touch()

    print(f"Split {len(images)} images → {len(splits['train'])} train / {len(splits['val'])} val")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="exports/raw", help="Unzipped Label Studio export")
    parser.add_argument("--dest", default="data", help="Output directory for YOLO training")
    parser.add_argument("--val-ratio", type=float, default=0.3)
    args = parser.parse_args()
    split(Path(args.src), Path(args.dest), args.val_ratio)
```

Run:

```bash
python split_dataset.py --src exports/raw --dest data
```

> **Why set a random seed?** `random.seed(42)` makes the shuffle reproducible — every time you run the script you get the same train/val split. This matters because if you retrain the model and want to compare results fairly, you need the same images in each set. Changing the seed (or not setting one) would give a different split, making comparisons unreliable.

---

## 6. Stage 2 — Training

### 6.1 Two-Model Architecture

Because wet/dry is an image-level attribute, train two separate models:

| Model | Task | Architecture |
|---|---|---|
| `style_classifier` | wet vs dry — whole image | `yolov8n-cls.pt` (classification) |
| `ingredient_detector` | bounding boxes for 10 ingredient classes | `yolov8n.pt` (detection) |

This cleanly separates concerns and avoids the overlap problem.

> **Classification vs detection:** A **classifier** looks at the whole image and outputs one label (wet or dry). A **detector** scans the image in a grid, predicts bounding boxes around objects, and assigns a class label to each box. They are different model architectures solving different types of problems.

### 6.2 Install

```bash
pip install ultralytics pandas tqdm scikit-learn
```

### 6.3 Dataset Configs

**Ingredient detection** — `data/ingredients.yaml`:

```yaml
path: ./data
train: images/train
val: images/val

nc: 10
names:
  - prawns
  - squid
  - pork_belly
  - pork_lard
  - egg
  - bean_sprouts
  - fish_cake
  - sambal
  - calamansi
  - chives
```

> **What is `nc`?** `nc` stands for "number of classes". YOLO uses this to set the size of its output layer — one output slot per class. If you later add or remove a class, you must update `nc` and retrain from scratch (the model architecture changes). This is why deferring sparse classes before your first training run avoids wasted effort.

**Style classification** — Label Studio exports the image-level choice as a separate JSON. Create `data/style/train/wet/` and `data/style/train/dry/` directories and sort images by their labelled style. The `split_dataset.py` script can be extended to handle this; note it in the implementation tasks.

### 6.4 Training Scripts

**Ingredient detector** — `train_detector.py`:

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
model.train(
    data="data/ingredients.yaml",
    epochs=50,
    imgsz=640,
    batch=16,
    name="ingredients_v1",
    patience=10,
    save=True,
    plots=True,
)
```

**Style classifier** — `train_classifier.py`:

```python
from ultralytics import YOLO

model = YOLO("yolov8n-cls.pt")
model.train(
    data="data/style",   # directory with train/wet, train/dry, val/wet, val/dry
    epochs=30,
    imgsz=224,
    batch=16,
    name="style_v1",
    patience=10,
)
```

> **Key training parameters explained:**
> - `epochs=50` — how many times the model sees all training images. More epochs = more learning, but also more risk of overfitting. `patience=10` stops training early if validation performance has not improved for 10 consecutive epochs, saving time.
> - `imgsz=640` — all images are resized to 640×640 pixels before being fed to the detector. Larger = more detail but slower training. The classifier uses 224×224, which is smaller because it only needs to classify the overall dish style, not localise small objects.
> - `batch=16` — how many images the model processes at once before updating its weights. Larger batches give more stable gradient estimates but require more memory. 16 is a safe default for most consumer hardware.

### 6.5 Model Size Guide

| Model | Speed | Accuracy | Use when |
|---|---|---|---|
| `yolov8n.pt` | Fastest | Lower | < 200 images, CPU only |
| `yolov8s.pt` | Fast | Moderate | 200–500 images |
| `yolov8m.pt` | Moderate | Good | 500+ images, GPU available |

Start with `yolov8n`. Upgrade once you have more labels.

> **The "n/s/m" suffix** refers to model size: nano, small, medium. Larger models have more parameters (internal numbers to learn), so they can represent more complex patterns — but they need more data to learn from and take longer to train. With a small dataset, a large model will overfit; a small model is the right starting point.

---

## 7. Stage 3 — Inference & Export

### 7.1 Inference Script

Create `analyse.py`:

```python
import argparse
import time
from pathlib import Path

import pandas as pd
from ultralytics import YOLO

INGREDIENT_LABELS = [
    "prawns", "squid", "pork_belly", "pork_lard", "egg",
    "bean_sprouts", "fish_cake", "sambal", "calamansi", "chives",
]

CONF_THRESHOLD = 0.35  # tune based on validation confusion matrix


def infer_style(classifier, image_path: Path) -> str:
    results = classifier(str(image_path), verbose=False)
    probs = results[0].probs
    top_label = classifier.names[probs.top1]
    # Flag conflict if top confidence is low (model is uncertain)
    if probs.top1conf < 0.55:
        return "unknown"
    return top_label  # "wet" or "dry"


def infer_ingredients(detector, image_path: Path) -> dict:
    results = detector(str(image_path), conf=CONF_THRESHOLD, verbose=False)
    detected = {detector.names[int(cls)] for cls in results[0].boxes.cls}
    return {label: label in detected for label in INGREDIENT_LABELS}


def timestamped_path(base: Path) -> Path:
    if base.exists():
        ts = time.strftime("%Y%m%d-%H%M%S")
        return base.with_name(f"{base.stem}_{ts}{base.suffix}")
    return base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="images/")
    parser.add_argument("--detector-weights", default="runs/detect/ingredients_v1/weights/best.pt")
    parser.add_argument("--classifier-weights", default="runs/classify/style_v1/weights/best.pt")
    parser.add_argument("--output", default="output/results.csv")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    image_dir = Path(args.input)
    images = sorted(image_dir.glob("*.jpg")) + sorted(image_dir.glob("*.png"))

    if args.dry_run:
        print(f"Would process {len(images)} images.")
        for img in images:
            print(f"  {img}")
        return

    detector = YOLO(args.detector_weights)
    classifier = YOLO(args.classifier_weights)

    rows = []
    for img in images:
        style = infer_style(classifier, img)
        ingredients = infer_ingredients(detector, img)
        rows.append({
            "image_id": img.stem,
            "source_path": str(img),
            "style": style,
            **ingredients,
            "notes": "",
        })

    output_path = timestamped_path(Path(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)
    print(f"Saved {len(rows)} rows → {output_path}")


if __name__ == "__main__":
    main()
```

> **What does `best.pt` mean?** During training, YOLO saves the model weights after every epoch. `best.pt` is the checkpoint from the epoch that achieved the highest validation mAP — not necessarily the last epoch. Using `best.pt` rather than `last.pt` protects against the model overfitting in later epochs.

---

## 8. Fallback — LLM Assist (Optional)

Use this **only** when:
- You have fewer than ~50 images and cannot yet fine-tune reliably
- You want to bootstrap labels to speed up manual review in Label Studio

If needed, add a `--llm-fallback` flag to `analyse.py` that calls Claude vision on images where the classifier confidence is below threshold. This is a bridge, not the default path.

> **Why not just use an LLM for everything?** LLMs are flexible but inconsistent — the same image might get slightly different labels on two separate calls, and they have no awareness of your specific labelling conventions (e.g. "skip individual lard specks"). A fine-tuned YOLO model, once trained, is deterministic, fast, runs offline, and has been calibrated to your exact taxonomy.

---

## 9. Project Structure

```
hokkien-mee-analysis/
├── images/                    # raw input images
├── exports/
│   └── raw/                   # unzipped Label Studio export goes here
├── data/
│   ├── images/
│   │   ├── train/
│   │   └── val/
│   ├── labels/
│   │   ├── train/
│   │   └── val/
│   ├── style/
│   │   ├── train/
│   │   │   ├── wet/
│   │   │   └── dry/
│   │   └── val/
│   │       ├── wet/
│   │       └── dry/
│   └── ingredients.yaml
├── output/                    # timestamped CSVs written here
├── runs/                      # created by YOLO training
├── split_dataset.py
├── train_detector.py
├── train_classifier.py
├── analyse.py
└── requirements.txt
```

---

## 10. Implementation Tasks for Claude Code

**Group 1 — Scaffolding (run immediately):**

1. Create the full project directory structure above.
2. Write `requirements.txt`: `ultralytics`, `pandas`, `tqdm`, `scikit-learn`, `label-studio`.
3. Write `split_dataset.py` from Section 5, extended to also sort images into `data/style/train/wet|dry` using the Label Studio JSON export.

> **Pause after Group 1.** Do not proceed until Stage 1 labelling is complete and `exports/raw/` is populated.

**Group 2 — Model architecture (after labelling):**

4. Write `data/ingredients.yaml` from Section 6.3.
5. Write `train_detector.py` from Section 6.4.
6. Write `train_classifier.py` from Section 6.4.

> **Pause after Group 2.** Run both training scripts and review `results.png` and `confusion_matrix.png` before inference.

**Group 3 — Inference & docs:**

7. Write `analyse.py` from Section 7.1.
8. Write `README.md` with setup and usage instructions.

---

## 11. Acceptance Criteria

- `python analyse.py --dry-run` prints image list without loading any weights
- Output CSV matches the schema in Section 2 exactly (column names, types)
- `style` is one of `wet`, `dry`, `unknown` — never empty
- Script does not crash on images with no detections (all ingredient columns `False`)
- Re-running writes a new timestamped file; it never silently overwrites
- `split_dataset.py` produces non-overlapping train/val sets (no image appears in both)

---

## 12. Iterating on the Model

After your first training run, check `runs/` for:

- `results.png` — training/val loss and mAP curves
- `confusion_matrix.png` — per-class performance

**Reading the loss curves:** Training loss should decrease steadily. Validation loss should also decrease, then level off. If validation loss starts *increasing* while training loss continues to fall, the model is overfitting — it is memorising training images rather than learning general rules. The fix is more labelled data, or using a smaller model (`yolov8n` instead of `yolov8s`).

**Reading the confusion matrix:** Each row is the true class; each column is what the model predicted. A perfect model has all mass on the diagonal (predicted = actual). Off-diagonal entries reveal which classes get confused with each other. For example, if `pork_lard` is frequently predicted as `egg`, your labels for those two classes may not be visually distinct enough, or you need more examples of each.

**If mAP50 < 0.5 overall:**
- Add more labelled images for the weakest classes
- Lower `CONF_THRESHOLD` in `analyse.py`
- Upgrade from `yolov8n` to `yolov8s`

**If a specific class is consistently missed (e.g. `pork_lard`):**
- Accept it is too visually ambiguous at this dataset size
- Set a `low_confidence_classes` list in `analyse.py` and write a flag to `notes` rather than a hard boolean

**If false positives are high:**
- Raise `CONF_THRESHOLD`
- Review and correct labels in Label Studio, then retrain

**Class deferral:** If `chives` or `fish_cake` have fewer than 10 examples in training data after your first collection round, remove them from `ingredients.yaml`, retrain, and re-add once you have sufficient examples.
