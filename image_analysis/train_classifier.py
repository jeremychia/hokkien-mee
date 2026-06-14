"""
Train a YOLOv8 image classifier for wet/dry style detection.

Run from repo root after split_dataset.py:
    uv run python image_analysis/train_classifier.py
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLOv8 wet/dry style classifier")
    parser.add_argument("--data", default="image_analysis/data/style")
    parser.add_argument("--model", default="yolov8n-cls.pt", help="Base weights (auto-downloaded if absent)")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--name", default="style_v1")
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--device", default="", help="cuda device or '' for auto")
    parser.add_argument("--project", default=None,
                        help="Output directory for runs (default: image_analysis/runs/classify relative to repo root)")
    args = parser.parse_args()

    data_path = Path(args.data).resolve()
    train_wet = data_path / "train" / "wet"
    train_dry = data_path / "train" / "dry"

    for class_dir in (train_wet, train_dry):
        if not class_dir.exists() or not any(class_dir.iterdir()):
            print(
                f"Error: {class_dir} is empty or missing.\n"
                "Run split_dataset.py first and ensure images have style labels.",
                file=sys.stderr,
            )
            sys.exit(1)

    n_wet = sum(1 for _ in train_wet.glob("*.*"))
    n_dry = sum(1 for _ in train_dry.glob("*.*"))
    print(f"Training style images — wet: {n_wet}, dry: {n_dry}")

    min_class = min(n_wet, n_dry)
    minority = "wet" if n_wet < n_dry else "dry"
    if min_class < 10:
        print(
            f"Warning: class '{minority}' has only {min_class} training images — "
            "classifier may not learn reliably. Label more examples before training."
        )

    project = Path(args.project).resolve() if args.project else Path("image_analysis/runs/classify").resolve()

    from ultralytics import YOLO

    model = YOLO(args.model)
    try:
        model.train(
            data=str(data_path),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            name=args.name,
            patience=args.patience,
            device=args.device,
            project=str(project),
        )
    except RuntimeError as e:
        if "out of memory" in str(e).lower():
            print(f"\nOOM error: try reducing --batch (current: {args.batch})")
        raise

    best_weights = project / args.name / "weights" / "best.pt"
    print(f"\nBest weights: {best_weights}")
    print(f"Review training results before running analyse.py:")
    print(f"  {project / args.name / 'results.png'}")


if __name__ == "__main__":
    main()
