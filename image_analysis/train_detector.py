"""
Train a YOLOv8 ingredient detection model.

Run from repo root after split_dataset.py:
    uv run python image_analysis/train_detector.py
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLOv8 ingredient detector")
    parser.add_argument("--data", default="image_analysis/data/ingredients.yaml")
    parser.add_argument("--model", default="yolov8n.pt", help="Base weights (auto-downloaded if absent)")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--name", default="ingredients_v1")
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--device", default="", help="cuda device or '' for auto")
    parser.add_argument("--project", default=None,
                        help="Output directory for runs (default: image_analysis/runs/detect relative to repo root)")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Error: {data_path} not found. Run split_dataset.py first.", file=sys.stderr)
        sys.exit(1)

    train_images = Path("image_analysis/data/images/train")
    if not train_images.exists() or not any(train_images.iterdir()):
        print(f"Error: {train_images} is empty or missing. Run split_dataset.py first.", file=sys.stderr)
        sys.exit(1)

    n_train = sum(1 for _ in train_images.glob("*.*"))
    print(f"Training images: {n_train}")
    if n_train < 20:
        print("Warning: fewer than 20 training images — model is unlikely to converge. Label more images first.")

    project = Path(args.project).resolve() if args.project else Path("image_analysis/runs/detect").resolve()

    from ultralytics import YOLO

    model = YOLO(args.model)
    try:
        model.train(
            data=str(data_path.resolve()),
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            name=args.name,
            patience=args.patience,
            device=args.device,
            project=str(project),
            save=True,
            plots=True,
        )
    except RuntimeError as e:
        if "out of memory" in str(e).lower():
            print(f"\nOOM error: try reducing --batch (current: {args.batch}) or --imgsz (current: {args.imgsz})")
        raise

    best_weights = project / args.name / "weights" / "best.pt"
    print(f"\nBest weights: {best_weights}")
    print(f"Review training results before running analyse.py:")
    print(f"  {project / args.name / 'results.png'}")
    print(f"  {project / args.name / 'confusion_matrix.png'}")


if __name__ == "__main__":
    main()
