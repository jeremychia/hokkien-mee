"""
Run inference on noodle images and produce a timestamped CSV.

Reads output/image_labels.json, filters to image_type == "noodles", applies
the trained ingredient detector and style classifier, and writes one row per
image matching the output schema.

Run from repo root:
    uv run python image_analysis/analyse.py --dry-run
    uv run python image_analysis/analyse.py
"""

import argparse
import json
import sys
import time
from pathlib import Path

from image_analysis import INGREDIENTS

CONF_THRESHOLD = 0.35
STYLE_CONF_THRESHOLD = 0.55


def _timestamped_path(base: Path) -> Path:
    if not base.exists():
        return base
    ts = time.strftime("%Y%m%d-%H%M%S")
    return base.with_name(f"{base.stem}_{ts}{base.suffix}")


def _infer_style(classifier, image_path: Path, style_conf: float) -> tuple[str, float]:
    results = classifier(str(image_path), verbose=False)
    probs = results[0].probs
    conf = float(probs.top1conf)
    if conf < style_conf:
        return "unknown", conf
    return classifier.names[probs.top1], conf


def _infer_ingredients_with_boxes(detector, image_path: Path, conf: float) -> tuple[dict[str, bool], list[dict]]:
    """Returns (boolean ingredient dict, list of raw box dicts for Label Studio export)."""
    results = detector(str(image_path), conf=conf, verbose=False)
    boxes = results[0].boxes
    detected: set[str] = set()
    raw_boxes = []

    if len(boxes) > 0:
        orig_h, orig_w = results[0].orig_shape
        for box in boxes:
            cls_name = detector.names[int(box.cls)]
            detected.add(cls_name)
            # box.xywhn is normalised [cx, cy, w, h]
            cx, cy, w, h = box.xywhn[0].tolist()
            raw_boxes.append({
                "label": cls_name,
                "x": round((cx - w / 2) * 100, 2),
                "y": round((cy - h / 2) * 100, 2),
                "width": round(w * 100, 2),
                "height": round(h * 100, 2),
                "score": round(float(box.conf), 3),
                "original_width": orig_w,
                "original_height": orig_h,
            })

    return {name: name in detected for name in INGREDIENTS}, raw_boxes


def _infer_ingredients(detector, image_path: Path, conf: float) -> dict[str, bool]:
    results = detector(str(image_path), conf=conf, verbose=False)
    boxes = results[0].boxes
    if len(boxes) == 0:
        detected: set[str] = set()
    else:
        detected = {detector.names[int(cls)] for cls in boxes.cls}
    return {name: name in detected for name in INGREDIENTS}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run inference on noodle images → CSV")
    parser.add_argument("--labels", default="output/image_labels.json")
    parser.add_argument(
        "--detector-weights",
        default="image_analysis/runs/detect/ingredients_v1/weights/best.pt",
    )
    parser.add_argument(
        "--classifier-weights",
        default="image_analysis/runs/classify/style_v1/weights/best.pt",
    )
    parser.add_argument("--output", default="output/results.csv")
    parser.add_argument("--conf", type=float, default=CONF_THRESHOLD)
    parser.add_argument("--style-conf", type=float, default=STYLE_CONF_THRESHOLD)
    parser.add_argument("--dry-run", action="store_true", help="Print image list without running inference")
    parser.add_argument("--no-filter", action="store_true", help="Process all images regardless of image_type")
    parser.add_argument("--label-studio-output", default=None,
                        help="If set, also write a Label Studio predictions JSON to this path")
    args = parser.parse_args()

    labels_path = Path(args.labels)
    if not labels_path.exists():
        print(f"Error: {labels_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(labels_path) as f:
        records = json.load(f)

    if args.no_filter:
        candidates = records
    else:
        candidates = [r for r in records if r.get("image_type") == "noodles"]

    images: list[tuple[str, Path]] = []
    skipped = 0
    for r in candidates:
        local_path = r.get("local_path", "")
        p = Path(local_path)
        if not p.exists():
            skipped += 1
            continue
        images.append((r["image_id"], p))

    if args.dry_run:
        print(f"Would process {len(images)} images ({skipped} skipped — missing files):")
        for image_id, p in images[:10]:
            print(f"  {image_id}: {p}")
        if len(images) > 10:
            print(f"  ... and {len(images) - 10} more")
        return

    if skipped:
        print(f"Warning: {skipped} images skipped (missing files)")

    detector_path = Path(args.detector_weights)
    classifier_path = Path(args.classifier_weights)
    for weights, label in ((detector_path, "detector"), (classifier_path, "classifier")):
        if not weights.exists():
            print(
                f"Error: {label} weights not found at {weights}.\n"
                f"Run train_{'detector' if label == 'detector' else 'classifier'}.py first.",
                file=sys.stderr,
            )
            sys.exit(1)

    from tqdm import tqdm
    from ultralytics import YOLO
    import pandas as pd

    detector = YOLO(str(detector_path))
    classifier = YOLO(str(classifier_path))

    rows = []
    ls_tasks = [] if args.label_studio_output else None
    errors = 0
    for image_id, img_path in tqdm(images, desc="Inferring"):
        try:
            style, style_conf = _infer_style(classifier, img_path, args.style_conf)
            ingredients, raw_boxes = _infer_ingredients_with_boxes(detector, img_path, args.conf)
            notes = ""
        except Exception as e:
            print(f"  inference_error on {img_path}: {e}")
            style = "unknown"
            style_conf = 0.0
            ingredients = {name: False for name in INGREDIENTS}
            raw_boxes = []
            notes = "inference_error"
            errors += 1

        post_id = image_id.rsplit("_", 1)[0]
        rows.append({
            "image_id": image_id,
            "post_id": post_id,
            "source_path": str(img_path),
            "style": style,
            "style_confidence": round(style_conf, 4),
            **ingredients,
            "notes": notes,
        })

        if ls_tasks is not None:
            ls_results = []
            uid = 0
            if style in ("wet", "dry"):
                ls_results.append({
                    "id": f"r{uid}",
                    "type": "choices",
                    "from_name": "style",
                    "to_name": "image",
                    "value": {"choices": [style]},
                })
                uid += 1
            for box in raw_boxes:
                ls_results.append({
                    "id": f"r{uid}",
                    "type": "rectanglelabels",
                    "from_name": "label",
                    "to_name": "image",
                    "value": {
                        "x": box["x"],
                        "y": box["y"],
                        "width": box["width"],
                        "height": box["height"],
                        "rectanglelabels": [box["label"]],
                    },
                    "score": box["score"],
                })
                uid += 1
            ls_tasks.append({
                "data": {"image": f"/data/local-files/?d={img_path}"},
                "predictions": [{"model_version": detector_path.parent.parent.name, "result": ls_results}],
            })

    column_order = ["image_id", "post_id", "source_path", "style", "style_confidence", *INGREDIENTS, "notes"]
    df = pd.DataFrame(rows, columns=column_order)

    output_path = _timestamped_path(Path(args.output))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"\nProcessed: {len(rows)} images ({errors} errors)")
    print(f"Saved → {output_path}")

    if ls_tasks is not None and args.label_studio_output:
        ls_path = _timestamped_path(Path(args.label_studio_output))
        ls_path.parent.mkdir(parents=True, exist_ok=True)
        ls_path.write_text(json.dumps(ls_tasks, indent=2))
        print(f"Label Studio predictions → {ls_path}")
        print("Import in Label Studio: Project → Import → upload this file")


if __name__ == "__main__":
    main()
