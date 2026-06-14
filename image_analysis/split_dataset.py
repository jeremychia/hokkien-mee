"""
Split a Label Studio JSON export into YOLO-format train/val directories and
style classification subdirectories.

Only one export is needed: Export → JSON from Label Studio.
The JSON contains both bounding boxes and style choices.

Image paths in the JSON use Label Studio's local-files URL format:
  /data/local-files/?d=output/images/<filename>.jpg
These are resolved relative to --repo-root (default: current directory).

Outputs (under --dest)
----------------------
data/images/train|val/        — for ingredient detector
data/labels/train|val/        — YOLO .txt annotation files
data/style/train|val/wet|dry/ — for style classifier

Run from repo root:
    uv run python image_analysis/split_dataset.py
"""

import argparse
import random
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import json

from sklearn.model_selection import StratifiedShuffleSplit

from image_analysis import INGREDIENTS


def _resolve_image_path(label_studio_url: str, repo_root: Path) -> Path | None:
    """
    Convert a Label Studio local-files URL to an absolute filesystem path.

    Handles two formats:
      /data/local-files/?d=output/images/foo.jpg   (local file storage)
      /data/upload/1/foo.jpg                        (uploaded files)
    """
    parsed = urlparse(label_studio_url)
    qs = parse_qs(parsed.query)

    if "d" in qs:
        # Local file storage: ?d= contains the relative path from DOCUMENT_ROOT
        rel = qs["d"][0]
        return repo_root / rel

    # Fallback: use the path component directly as a relative path
    path_part = parsed.path.lstrip("/")
    candidate = repo_root / path_part
    if candidate.exists():
        return candidate

    return None


def _parse_tasks(tasks: list, repo_root: Path) -> dict[str, dict]:
    """
    Returns {filename: {"style": str|None, "boxes": [yolo_line, ...], "image_path": Path}}
    """
    ingredient_index = {name: idx for idx, name in enumerate(INGREDIENTS)}
    result: dict[str, dict] = {}

    for task in tasks:
        if not task.get("annotations"):
            continue

        image_url = task.get("data", {}).get("image", "")
        image_path = _resolve_image_path(image_url, repo_root)
        if image_path is None or not image_path.exists():
            print(f"  Warning: image not found for URL {image_url!r} — skipping")
            continue

        filename = image_path.name
        style = None
        boxes = []

        # Use first (and typically only) annotation
        annotation = task["annotations"][0]
        for item in annotation.get("result", []):
            item_type = item.get("type")
            value = item.get("value", {})

            if item_type == "choices" and item.get("from_name") == "style":
                choices = value.get("choices", [])
                if choices:
                    style = choices[0].lower()

            elif item_type == "rectanglelabels":
                labels = value.get("rectanglelabels", [])
                if not labels:
                    continue
                label = labels[0]
                if label not in ingredient_index:
                    print(f"  Warning: unknown label {label!r} — skipping box")
                    continue

                x_pct = value.get("x", 0) / 100
                y_pct = value.get("y", 0) / 100
                w_pct = value.get("width", 0) / 100
                h_pct = value.get("height", 0) / 100

                cx = x_pct + w_pct / 2
                cy = y_pct + h_pct / 2

                class_idx = ingredient_index[label]
                boxes.append(f"{class_idx} {cx:.6f} {cy:.6f} {w_pct:.6f} {h_pct:.6f}")

        result[filename] = {"style": style, "boxes": boxes, "image_path": image_path}

    return result


def _clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def split(
    labels_json: Path,
    dest: Path,
    repo_root: Path,
    val_ratio: float,
    seed: int,
) -> None:
    if not labels_json.exists():
        print(f"Error: {labels_json} not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing Label Studio JSON: {labels_json}")
    with open(labels_json) as f:
        tasks = json.load(f)

    annotation_map = _parse_tasks(tasks, repo_root)
    if not annotation_map:
        print("Error: no valid annotated images found.", file=sys.stderr)
        sys.exit(1)

    all_filenames = list(annotation_map.keys())
    print(f"Valid annotated images: {len(all_filenames)}")

    # --- Train/val split for detection (random) ---
    rng = random.Random(seed)
    shuffled = list(all_filenames)
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_ratio))
    detection_splits = {"val": shuffled[:n_val], "train": shuffled[n_val:]}

    for split_name in ("train", "val"):
        _clean_dir(dest / "images" / split_name)
        _clean_dir(dest / "labels" / split_name)

    for split_name, split_files in detection_splits.items():
        for filename in split_files:
            entry = annotation_map[filename]
            shutil.copy(entry["image_path"], dest / "images" / split_name / filename)
            label_file = dest / "labels" / split_name / Path(filename).with_suffix(".txt").name
            if entry["boxes"]:
                label_file.write_text("\n".join(entry["boxes"]) + "\n")
            else:
                label_file.touch()  # empty = no detections, not unlabelled

    # --- Train/val split for style classifier (stratified) ---
    style_filenames = [f for f in all_filenames if annotation_map[f]["style"] in ("wet", "dry")]
    style_labels = [annotation_map[f]["style"] for f in style_filenames]
    no_style_count = len(all_filenames) - len(style_filenames)

    style_splits: dict[str, list] = {"train": [], "val": []}

    if len(style_filenames) >= 2 and len(set(style_labels)) == 2:
        splitter = StratifiedShuffleSplit(n_splits=1, test_size=val_ratio, random_state=seed)
        train_idx, val_idx = next(splitter.split(style_filenames, style_labels))
        style_splits["train"] = [style_filenames[i] for i in train_idx]
        style_splits["val"] = [style_filenames[i] for i in val_idx]
    else:
        print("  Warning: too few style-labelled images for stratified split; using random split")
        rng2 = random.Random(seed)
        shuffled_style = list(style_filenames)
        rng2.shuffle(shuffled_style)
        n_val_s = max(1, int(len(shuffled_style) * val_ratio))
        style_splits["val"] = shuffled_style[:n_val_s]
        style_splits["train"] = shuffled_style[n_val_s:]

    style_counts: dict[str, dict[str, int]] = {"train": {}, "val": {}}
    for split_name, split_files in style_splits.items():
        for filename in split_files:
            style = annotation_map[filename]["style"]
            out_dir = dest / "style" / split_name / style
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(annotation_map[filename]["image_path"], out_dir / filename)
            style_counts[split_name][style] = style_counts[split_name].get(style, 0) + 1

    print(f"\nIngredient detection:")
    print(f"  train: {len(detection_splits['train'])} images")
    print(f"  val:   {len(detection_splits['val'])} images")
    print(f"\nStyle classification:")
    for split_name in ("train", "val"):
        counts = style_counts[split_name]
        parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  {split_name}: {parts}")
    if no_style_count:
        print(f"\n  {no_style_count} images excluded from classifier (no style label)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split Label Studio JSON export into YOLO train/val dirs")
    parser.add_argument("--labels-json", default="image_analysis/exports/raw/annotations.json",
                        help="Label Studio JSON export")
    parser.add_argument("--dest", default="image_analysis/data")
    parser.add_argument("--repo-root", default=".",
                        help="Repo root — used to resolve local-files paths from Label Studio")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    split(
        labels_json=Path(args.labels_json),
        dest=Path(args.dest),
        repo_root=Path(args.repo_root).resolve(),
        val_ratio=args.val_ratio,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
