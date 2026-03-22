#!/usr/bin/env python3
"""
Classify downloaded images into noodles/storefront/other.

Usage:
  python extractor/classify_images.py --input output/group_posts.json --output output/image_labels.json

Outputs:
  - output/image_labels.json
  - output/image_labels.csv
  - output/image_classification_report.md

This is intentionally a lightweight step that can run after download_images and before map_posts.
"""

import argparse
import csv
import json
import math
import os
import sys
import time
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None


INPUT_DEFAULT = "output/group_posts.json"
OUTPUT_JSON_DEFAULT = "output/image_labels.json"
OUTPUT_CSV_DEFAULT = "output/image_labels.csv"
OUTPUT_REPORT_DEFAULT = "output/image_classification_report.md"
IMAGES_DIR = "output/images"
MODEL_CACHE_PATH = "output/finetuned_resnet.pth"
MODEL_CACHE_INFO_PATH = "output/finetuned_resnet_info.json"


def load_posts(input_path):
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"{input_path} not found. Run extract_group.py first.")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "posts" in data:
        return data["posts"]
    elif isinstance(data, list):
        return data
    else:
        raise ValueError("Unexpected JSON format in group_posts.json")


def load_imagenet_labels():
    try:
        import torchvision
    except ImportError:
        return None

    class_map = {}  # idx -> label string
    try:
        # torchvision provides labels in the following module for >=0.13
        from torchvision.models import resnet
    except Exception:
        pass

    # Fallback: try available ImageNet class names included in torchvision
    try:
        labels = torchvision.models.ResNet50_Weights.DEFAULT.meta["categories"]
        for i, name in enumerate(labels):
            class_map[i] = name
        return class_map
    except Exception:
        pass

    # Try to load from helper text if installed
    try:
        from torchvision.datasets import ImageNet
        # not available without data; skip
    except Exception:
        pass

    return None


def load_manual_labels(csv_path):
    """Load manual labels for fine-tuning."""
    if not os.path.exists(csv_path):
        return []
    manual = []
    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('is_manual', '').lower() == 'true':
                manual.append((row['local_path'], row['image_type']))
    return manual


def fine_tune_resnet(model, manual_labels):
    """Fine-tune ResNet on manual labels."""
    import torch
    from torch.utils.data import Dataset
    from torchvision import transforms
    from PIL import Image

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    class ImageDataset(Dataset):
        def __init__(self, data, transform):
            self.data = data
            self.transform = transform

        def __len__(self):
            return len(self.data)

        def __getitem__(self, idx):
            path, label = self.data[idx]
            image = Image.open(path).convert('RGB')
            image = self.transform(image)
            label_idx = {'noodles': 0, 'storefront': 1, 'other': 2}[label]
            return image, label_idx

    data = manual_labels
    dataset = ImageDataset(data, transform)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=4, shuffle=True)

    # Modify model for 3 classes
    model.fc = torch.nn.Linear(model.fc.in_features, 3)
    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    criterion = torch.nn.CrossEntropyLoss()

    model.train()
    for epoch in range(5):
        for images, labels in dataloader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
        print(f"Epoch {epoch+1}/5, Loss: {loss.item():.4f}")

    model.eval()

    # Save the fine-tuned model
    os.makedirs(os.path.dirname(MODEL_CACHE_PATH), exist_ok=True)
    torch.save(model.state_dict(), MODEL_CACHE_PATH)
    # Save info about the training data
    with open(MODEL_CACHE_INFO_PATH, 'w') as f:
        json.dump({'manual_labels_count': len(data)}, f)
    print(f"Saved fine-tuned model to {MODEL_CACHE_PATH}")

    return model


def get_model(fine_tune=False, manual_labels=None, force_retrain=False):
    if fine_tune and manual_labels:
        # Use ResNet and fine-tune
        try:
            import torch
            from torchvision import transforms
            from torchvision.models import resnet50
        except Exception:
            return None

        # Check for cached model
        if not force_retrain and os.path.exists(MODEL_CACHE_PATH) and os.path.exists(MODEL_CACHE_INFO_PATH):
            try:
                with open(MODEL_CACHE_INFO_PATH, 'r') as f:
                    cache_info = json.load(f)
                if cache_info.get('manual_labels_count') == len(manual_labels):
                    print(f"Loading cached fine-tuned model from {MODEL_CACHE_PATH}")
                    model = resnet50(weights="IMAGENET1K_V2")
                    model.fc = torch.nn.Linear(model.fc.in_features, 3)  # Adjust for 3 classes
                    model.load_state_dict(torch.load(MODEL_CACHE_PATH, map_location=torch.device('cpu')))
                    model.eval()
                    preprocess = transforms.Compose([
                        transforms.Resize(256),
                        transforms.CenterCrop(224),
                        transforms.ToTensor(),
                        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                    ])
                    return {
                        "model": model,
                        "preprocess": preprocess,
                        "torch": torch,
                        "type": "resnet_finetuned_cached",
                    }
                else:
                    print(f"Cached model has different number of labels ({cache_info.get('manual_labels_count')} vs {len(manual_labels)}), retraining...")
            except Exception as e:
                print(f"Failed to load cached model: {e}, retraining...")

        try:
            model = resnet50(weights="IMAGENET1K_V2")
        except Exception:
            try:
                model = resnet50(pretrained=True)
            except Exception as e:
                print(f"Warning: could not load torchvision model (skipping model-driven prediction): {e}")
                return None

        model.eval()

        preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        print(f"Fine-tuning ResNet on {len(manual_labels)} manual labels...")
        model = fine_tune_resnet(model, manual_labels)
        return {
            "model": model,
            "preprocess": preprocess,
            "torch": torch,
            "type": "resnet_finetuned",
        }
    else:
        # Try CLIP first (zero-shot)
        try:
            from transformers import CLIPProcessor, CLIPModel
            import torch
        except ImportError:
            pass
        else:
            try:
                model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
                processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
                return {
                    "model": model,
                    "processor": processor,
                    "torch": torch,
                    "type": "clip",
                }
            except Exception as e:
                print(f"Warning: could not load CLIP model: {e}")

        # Fallback to ResNet
        try:
            import torch
            from torchvision import transforms
            from torchvision.models import resnet50
        except Exception:
            return None

        try:
            model = resnet50(weights="IMAGENET1K_V2")
        except Exception:
            try:
                model = resnet50(pretrained=True)
            except Exception as e:
                print(f"Warning: could not load torchvision model (skipping model-driven prediction): {e}")
                return None

        model.eval()

        preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        labels = load_imagenet_labels() or {}
        return {
            "model": model,
            "preprocess": preprocess,
            "labels": labels,
            "torch": torch,
            "type": "resnet",
        }


def infer_image_label_with_model(image_path, pipeline):
    model_type = pipeline.get("type", "resnet")

    if model_type == "clip":
        return infer_with_clip(image_path, pipeline)
    elif model_type in ("resnet", "resnet_finetuned"):
        return infer_with_resnet(image_path, pipeline)
    else:
        return None


def infer_with_clip(image_path, pipeline):
    try:
        from PIL import Image
    except ImportError:
        return None

    model = pipeline.get("model")
    processor = pipeline.get("processor")
    torch = pipeline.get("torch")

    if model is None or processor is None or torch is None:
        return None

    try:
        image = Image.open(image_path).convert("RGB")
        # Prompts for zero-shot classification - multiple per class for better accuracy
        texts = [
            # Noodles
            "hokkien mee noodles in a bowl",
            "mee pok noodles dish",
            "kway teow noodles",
            "singapore noodles",
            # Storefront
            "hawker stall exterior",
            "food stall storefront",
            "restaurant front view",
            "shop front with signage",
            # Other
            "people eating",
            "cars and vehicles",
            "buildings and architecture",
            "other miscellaneous photo"
        ]

        inputs = processor(text=texts, images=image, return_tensors="pt", padding=True)
        with torch.no_grad():
            outputs = model(**inputs)
            logits_per_image = outputs.logits_per_image  # shape: [1, num_texts]
            probs = logits_per_image.softmax(dim=1)[0]  # shape: [num_texts]

            # Group probabilities by class
            noodle_probs = probs[:4]  # indices 0-3
            storefront_probs = probs[4:8]  # indices 4-7
            other_probs = probs[8:]  # indices 8-11

            # Average probabilities per class
            noodle_avg = torch.mean(noodle_probs).item()
            storefront_avg = torch.mean(storefront_probs).item()
            other_avg = torch.mean(other_probs).item()

            class_probs = [noodle_avg, storefront_avg, other_avg]
            top_prob = max(class_probs)
            top_idx = class_probs.index(top_prob)

            classes = ["noodles", "storefront", "other"]
            predicted_class = classes[top_idx]
            return predicted_class, top_prob
    except Exception as e:
        print(f"  Warning: CLIP inference failed for {image_path}: {e}")
        return None


def infer_with_resnet(image_path, pipeline):
    try:
        from PIL import Image
    except ImportError:
        return None

    model = pipeline.get("model")
    preprocess = pipeline.get("preprocess")
    labels = pipeline.get("labels", {})
    torch = pipeline.get("torch")

    if model is None or preprocess is None or torch is None:
        return None

    try:
        img = Image.open(image_path).convert("RGB")
        input_tensor = preprocess(img).unsqueeze(0)
        with torch.no_grad():
            logits = model(input_tensor)
            probs = torch.nn.functional.softmax(logits[0], dim=0)
            top_prob, top_idx = torch.max(probs, dim=0)
            top_idx = int(top_idx.item())
            top_prob = float(top_prob.item())

            if pipeline.get("type") == "resnet_finetuned":
                classes = ["noodles", "storefront", "other"]
                predicted_class = classes[top_idx]
                return predicted_class, top_prob
            else:
                top_label = labels.get(top_idx, "") if labels else ""
                mapped = map_imagenet_to_class(top_label)
                return mapped, top_prob
    except Exception as e:
        print(f"  Warning: ResNet inference failed for {image_path}: {e}")
        return None


def map_imagenet_to_class(imagenet_label):
    if not imagenet_label:
        return None

    label_lower = imagenet_label.lower()
    noodle_keywords = ["noodle", "ramen", "spaghetti", "soup", "plate", "dish", "food", "seafood", "breakfast", "pasta"]
    storefront_keywords = ["shop", "store", "building", "street", "door", "window", "restaurant", "sign", "storefront", "cafe"]

    if any(word in label_lower for word in noodle_keywords):
        return "noodles"
    if any(word in label_lower for word in storefront_keywords):
        return "storefront"

    # fallback based on top-level categories
    if "person" in label_lower or "people" in label_lower or "group" in label_lower:
        return "other"

    # If we see a food-related word, classify as noodles (even if generic)
    if "food" in label_lower or "gastronomy" in label_lower or "plate" in label_lower:
        return "noodles"

    return "other"


def heuristic_classify(image_path):
    name_lower = os.path.basename(image_path).lower()
    if any(k in name_lower for k in ["store", "shop", "front", "building", "sign", "restaurant", "stall"]):
        return "storefront", 0.5
    if any(k in name_lower for k in ["noodle", "mee", "hokkien", "plate", "food", "soup", "prawn"]):
        return "noodles", 0.5
    return "other", 0.5


def classify_image(image_path, classifier):
    if not os.path.exists(image_path):
        raise FileNotFoundError(image_path)

    result = {
        "image_type": "other",
        "confidence": 0.0,
        "reason": "unclassified",
        "model_source": "heuristic",
    }

    if classifier is not None:
        model_type = classifier.get("type", "resnet")
        if model_type == "clip":
            infer = infer_image_label_with_model(image_path, classifier)
            if infer:
                predicted_class, prob = infer
                result["image_type"] = predicted_class
                result["confidence"] = float(prob)
                result["reason"] = f"clip zero-shot"
                result["model_source"] = "clip"
                return result
        elif model_type == "resnet_finetuned":
            infer = infer_image_label_with_model(image_path, classifier)
            if infer:
                label, prob = infer
                result["image_type"] = label
                result["confidence"] = float(prob)
                result["reason"] = "finetuned resnet"
                result["model_source"] = "finetuned_resnet"
                return result
        elif model_type == "resnet":
            infer = infer_image_label_with_model(image_path, classifier)
            if infer:
                imagenet_label, prob = infer
                mapped = map_imagenet_to_class(imagenet_label)
                if mapped:
                    result["image_type"] = mapped
                    result["confidence"] = float(prob)
                    result["reason"] = f"imagenet:{imagenet_label}"
                    result["model_source"] = "imagenet_resnet"
                    return result

    # Fallback to heuristic
    rule_label, rule_conf = heuristic_classify(image_path)
    result["image_type"] = rule_label
    result["confidence"] = float(rule_conf)
    result["reason"] = "heuristic based on filename"
    result["model_source"] = "heuristic"
    return result


def write_json(output_path, data):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_existing_labels(csv_path):
    """Load existing labels from CSV, return dict by local_path with type and is_manual."""
    if not os.path.exists(csv_path):
        return {}
    existing = {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            path = row.get("local_path", "")
            typ = row.get("image_type", "other")
            manual = row.get("is_manual", "false").lower() == "true"
            if path:
                existing[path] = {"type": typ, "is_manual": manual}
    return existing


def write_csv(output_path, rows):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        # Columns: local_path, image_type, is_manual
        writer = csv.DictWriter(f, fieldnames=["local_path", "image_type", "is_manual"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "local_path": row.get("local_path", ""),
                "image_type": row.get("image_type", "other"),
                "is_manual": "true" if row.get("is_manual", False) else "false",
            })


def write_report(output_path, rows):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    by_type = {"noodles": [], "storefront": [], "other": []}

    for row in rows:
        t = row.get("image_type", "other")
        if t not in by_type:
            t = "other"
        by_type[t].append(row)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Image Classification Report\n\n")
        for label in ["noodles", "storefront", "other"]:
            items = by_type[label]
            auto_items = [r for r in items if not r.get("is_manual", False)]
            manual_count = len(items) - len(auto_items)
            f.write(f"## {label} (count={len(items)}, manual={manual_count}, auto={len(auto_items)})\n\n")
            if auto_items:
                auto_sorted = sorted(auto_items, key=lambda r: r.get("confidence", 0), reverse=True)
                f.write("### Highest Confidence (Auto)\n")
                top = auto_sorted[:10]
                for r in top:
                    f.write(f"- {r['image_id']} ({r['confidence']:.4f}) {r['local_path']} [{r['reason']}]\n")
                f.write("\n### Lowest Confidence (Auto)\n")
                bottom = auto_sorted[-10:] if len(auto_sorted) >= 5 else auto_sorted
                for r in bottom:
                    f.write(f"- {r['image_id']} ({r['confidence']:.4f}) {r['local_path']} [{r['reason']}]\n")
                f.write("\n")
            else:
                f.write("No auto-classified images.\n\n")


def print_preview(rows, n):
    n = min(n, len(rows))
    if n <= 0:
        return

    print(f"\nPreview first {n} label rows:")
    print("image_id\tpost_id\timage_type\tconfidence\tlocal_path\treason")
    for r in rows[:n]:
        print(f"{r['image_id']}\t{r['post_id']}\t{r['image_type']}\t{r['confidence']:.4f}\t{r['local_path']}\t{r['reason']}")


def main():
    parser = argparse.ArgumentParser(description="Classify images into noodles/storefront/other")
    parser.add_argument("--input", default=INPUT_DEFAULT, help="Path to group_posts.json")
    parser.add_argument("--output", default=OUTPUT_JSON_DEFAULT, help="Path to output image_labels.json")
    parser.add_argument("--csv", default=OUTPUT_CSV_DEFAULT, help="Path to output CSV")
    parser.add_argument("--report", default=OUTPUT_REPORT_DEFAULT, help="Path to output markdown report")
    parser.add_argument("--preview", type=int, default=10, help="Show top N rows after classification")
    parser.add_argument("--skip-model", action="store_true", help="Skip model-based classification and use heuristic only")
    parser.add_argument("--merge-existing", action="store_true", help="Load existing labels from CSV and only classify unclassified images")
    parser.add_argument("--reclassify-all", action="store_true", help="Reclassify all images, ignoring existing auto-classifications (preserves manual labels)")
    parser.add_argument("--only-new", action="store_true", help="Only classify images not present in existing CSV")
    parser.add_argument("--fine-tune", action="store_true", help="Fine-tune the model on manual labels before classification")
    parser.add_argument("--force-retrain", action="store_true", help="Force retraining even if cached model exists")
    parser.add_argument("--confidence-threshold", type=float, default=0.5, help="Minimum confidence to accept classification, else classify as 'other'")
    args = parser.parse_args()

    posts = load_posts(args.input)
    if not isinstance(posts, list):
        raise RuntimeError("Unexpected posts data")

    existing_labels = {}
    mode = "all"  # default: classify all
    if args.only_new:
        mode = "only_new"
        if os.path.exists(args.csv):
            existing_labels = load_existing_labels(args.csv)
            print(f"Loaded {len(existing_labels)} existing labels from {args.csv} (only classifying new images)")
        else:
            print("No existing CSV found, classifying all images")
    elif args.reclassify_all:
        mode = "reclassify_all"
        if os.path.exists(args.csv):
            existing_labels = load_existing_labels(args.csv)
            print(f"Loaded {len(existing_labels)} existing labels from {args.csv} (reclassifying auto-labeled, preserving manual)")
        else:
            print("No existing CSV found, classifying all images")
    elif args.merge_existing:
        mode = "merge_existing"
        if os.path.exists(args.csv):
            existing_labels = load_existing_labels(args.csv)
            print(f"Loaded {len(existing_labels)} existing labels from {args.csv} (preserving manual labels)")
        else:
            print("No existing CSV found, classifying all images")

    manual_labels = load_manual_labels(args.csv) if os.path.exists(args.csv) else []
    manual_count = len(manual_labels)
    total_existing = len(existing_labels)
    print(f"Existing labels: {total_existing} (manual={manual_count}, auto={total_existing - manual_count})")

    if args.fine_tune and not manual_labels:
        print("Warning: --fine-tune specified but no manual labels found in CSV. Skipping fine-tuning.")
        args.fine_tune = False

    classifier = None
    if not args.skip_model:
        classifier = get_model(fine_tune=args.fine_tune, manual_labels=manual_labels, force_retrain=args.force_retrain)

    rows = []
    missed = 0

    # Count total images for progress bar
    total_images = sum(len(post.get("images", [])) for post in posts if isinstance(post.get("images"), list))

    start_time = time.time()
    print(f"Starting classification of {total_images} images...")

    # Use tqdm for progress bar if available
    if tqdm is not None:
        progress_bar = tqdm(total=total_images, desc="Classifying images", unit="img")
    else:
        progress_bar = None

    for post in posts:
        post_id = str(post.get("post_id", "unknown"))
        image_urls = post.get("images", [])
        if not isinstance(image_urls, list):
            continue

        for i, img_url in enumerate(image_urls):
            image_id = f"{post_id}_{i}"
            local_path = os.path.join(IMAGES_DIR, f"{image_id}.jpg")
            source_url = img_url

            if not os.path.exists(local_path):
                print(f"Warning: local image not found, skipping: {local_path}")
                missed += 1
                if progress_bar:
                    progress_bar.update(1)
                continue

            # Determine if we should classify this image
            existing = existing_labels.get(local_path)
            should_classify = True
            is_manual = False

            # Always preserve existing manual labels
            if existing and existing["is_manual"]:
                should_classify = False
                is_manual = True
                classification = {
                    "image_type": existing["type"],
                    "confidence": 1.0,
                    "reason": "manual override",
                    "model_source": "manual",
                }
            elif mode == "only_new":
                should_classify = existing is None
            elif mode == "reclassify_all":
                # Manual labels already handled above
                pass  # should_classify = True for auto or new
            elif mode == "merge_existing":
                # Manual labels already handled above
                pass  # should_classify = True for auto or new
            # else: mode == "all", should_classify = True

            if should_classify:
                classification = classify_image(local_path, classifier)
                is_manual = False
            elif not is_manual:
                # For existing auto-classified, reuse the old classification
                if existing:
                    classification = {
                        "image_type": existing["type"],
                        "confidence": 0.5,  # placeholder
                        "reason": "existing auto-classification",
                        "model_source": "cached",
                    }
                else:
                    classification = classify_image(local_path, classifier)

            # Apply confidence threshold for non-manual classifications
            if not is_manual and classification["confidence"] < args.confidence_threshold:
                classification["image_type"] = "other"
                classification["reason"] = f"low confidence ({classification['confidence']:.2f}), {classification['reason']}"

            row = {
                "image_id": image_id,
                "post_id": post_id,
                "source_url": source_url,
                "local_path": local_path,
                "image_type": classification["image_type"],
                "confidence": classification["confidence"],
                "model_source": classification["model_source"],
                "reason": classification["reason"],
                "is_manual": is_manual,
            }
            rows.append(row)

            if progress_bar:
                progress_bar.update(1)

    if progress_bar:
        progress_bar.close()

    end_time = time.time()
    duration = end_time - start_time
    processed = len(rows)
    rate = processed / duration if duration > 0 else 0

    print(f"Done. Classified {processed} images, skipped {missed} missing images.")
    print(f"Total time: {duration:.2f}s ({rate:.1f} images/second)")

    write_json(args.output, rows)
    write_csv(args.csv, rows)
    write_report(args.report, rows)
    print(f"Wrote {args.output}, {args.csv}, {args.report}.")

    if args.preview > 0:
        print_preview(rows, args.preview)


if __name__ == "__main__":
    main()
