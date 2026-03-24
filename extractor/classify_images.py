#!/usr/bin/env python3
"""
Classify downloaded images into noodles/storefront/other.

Usage:
  python extractor/classify_images.py [--input INPUT] [--output OUTPUT]

Model selection (automatic — no flags needed):
  - Manual labels exist + valid cache  → load cached fine-tuned ResNet.
  - Manual labels exist + stale/no cache → fine-tune ResNet and cache.
  - No manual labels                   → zero-shot CLIP, or base ResNet as fallback.

Manual labels in the CSV are NEVER overwritten.

Outputs:
  - output/image_labels.json
  - output/image_labels.csv
  - output/image_classification_report.md
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
        transforms.RandomCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
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


def cross_validate_resnet(manual_labels, k=5):
    """Run k-fold CV on manual labels and print per-fold accuracy."""
    import torch
    from torch.utils.data import Dataset, Subset
    from torchvision import transforms
    from torchvision.models import resnet50
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
            return self.transform(image), {'noodles': 0, 'storefront': 1, 'other': 2}[label]

    dataset = ImageDataset(manual_labels, transform)
    fold_size = math.ceil(len(manual_labels) / k)
    indices = list(range(len(manual_labels)))
    fold_accuracies = []

    for fold in range(k):
        val_indices = indices[fold * fold_size: (fold + 1) * fold_size]
        train_indices = [i for i in indices if i not in val_indices]
        if not train_indices or not val_indices:
            continue

        train_loader = torch.utils.data.DataLoader(Subset(dataset, train_indices), batch_size=4, shuffle=True)
        val_loader = torch.utils.data.DataLoader(Subset(dataset, val_indices), batch_size=4)

        model = resnet50(weights="IMAGENET1K_V2")
        model.fc = torch.nn.Linear(model.fc.in_features, 3)
        model = model.to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
        criterion = torch.nn.CrossEntropyLoss()

        model.train()
        for _ in range(5):
            for images, labels in train_loader:
                images, labels = images.to(device), labels.to(device)
                optimizer.zero_grad()
                criterion(model(images), labels).backward()
                optimizer.step()

        model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                correct += (model(images).argmax(dim=1) == labels).sum().item()
                total += labels.size(0)

        acc = correct / total if total > 0 else 0
        fold_accuracies.append(acc)
        print(f"  CV fold {fold+1}/{k}: accuracy = {acc:.2%}")

    mean_acc = sum(fold_accuracies) / len(fold_accuracies) if fold_accuracies else 0
    print(f"  CV mean accuracy: {mean_acc:.2%}")
    return mean_acc


def get_model(manual_labels=None):
    """
    Return a classifier pipeline.

    - With manual labels and a valid cache (same label count): load cached fine-tuned ResNet.
    - With manual labels but stale / missing cache: fine-tune ResNet and cache.
    - Without manual labels: zero-shot CLIP, or base ResNet as fallback.
    """
    if manual_labels:
        try:
            import torch
            from torchvision import transforms
            from torchvision.models import resnet50
        except Exception as e:
            print(f"Warning: torchvision not available ({e}), falling back to zero-shot model")
            return _get_zeroshot_model()

        preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        # Try loading a valid cached model first
        if os.path.exists(MODEL_CACHE_PATH) and os.path.exists(MODEL_CACHE_INFO_PATH):
            try:
                with open(MODEL_CACHE_INFO_PATH, "r") as f:
                    cache_info = json.load(f)
                if cache_info.get("manual_labels_count") == len(manual_labels):
                    print(f"Loading cached fine-tuned model ({len(manual_labels)} manual labels)")
                    model = resnet50(weights="IMAGENET1K_V2")
                    model.fc = torch.nn.Linear(model.fc.in_features, 3)
                    model.load_state_dict(torch.load(MODEL_CACHE_PATH, map_location=torch.device("cpu")))
                    model.eval()
                    return {"model": model, "preprocess": preprocess, "torch": torch, "type": "resnet_finetuned"}
                print(f"Label count changed ({cache_info.get('manual_labels_count')} → {len(manual_labels)}), retraining...")
            except Exception as e:
                print(f"Cache load failed ({e}), retraining...")

        # Fine-tune from scratch
        try:
            model = resnet50(weights="IMAGENET1K_V2")
        except Exception:
            model = resnet50(pretrained=True)
        model.eval()
        print(f"Fine-tuning ResNet on {len(manual_labels)} manual labels...")
        if len(manual_labels) >= 10:
            print(f"Running {min(5, len(manual_labels))}-fold cross-validation...")
            cross_validate_resnet(manual_labels, k=min(5, len(manual_labels)))
        model = fine_tune_resnet(model, manual_labels)
        return {"model": model, "preprocess": preprocess, "torch": torch, "type": "resnet_finetuned"}

    return _get_zeroshot_model()


def _get_zeroshot_model():
    """Zero-shot CLIP classifier, with base ResNet as fallback."""
    try:
        from transformers import CLIPProcessor, CLIPModel
        import torch
        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        return {"model": model, "processor": processor, "torch": torch, "type": "clip"}
    except Exception as e:
        print(f"CLIP not available ({e}), trying base ResNet")

    try:
        import torch
        from torchvision import transforms
        from torchvision.models import resnet50
        model = resnet50(weights="IMAGENET1K_V2")
        model.eval()
        preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        labels = load_imagenet_labels() or {}
        return {"model": model, "preprocess": preprocess, "labels": labels, "torch": torch, "type": "resnet"}
    except Exception as e:
        print(f"Warning: could not load any model ({e})")
        return None


def infer_image_label_with_model(image_path, pipeline):
    model_type = pipeline.get("type", "resnet")
    if model_type == "clip":
        return infer_with_clip(image_path, pipeline)
    return infer_with_resnet(image_path, pipeline)


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

    if classifier is not None:
        infer = infer_image_label_with_model(image_path, classifier)
        if infer:
            predicted_class, prob = infer
            model_type = classifier.get("type", "resnet")
            return {
                "image_type": predicted_class,
                "confidence": float(prob),
                "reason": model_type,
                "model_source": model_type,
            }

    # Fallback to heuristic
    rule_label, rule_conf = heuristic_classify(image_path)
    return {
        "image_type": rule_label,
        "confidence": float(rule_conf),
        "reason": "heuristic based on filename",
        "model_source": "heuristic",
    }


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

    needs_review = sorted(
        [r for r in rows if not r.get("is_manual") and r.get("confidence", 1.0) < 0.65],
        key=lambda r: r.get("confidence", 0),
    )
    f.write(f"## Needs Manual Review (confidence < 0.65, count={len(needs_review)})\n\n")
    if needs_review:
        for r in needs_review[:30]:
            f.write(f"- {r['image_id']} ({r['confidence']:.4f}) {r['local_path']} → `{r['image_type']}`\n")
    else:
        f.write("No images need review.\n")
    f.write("\n")


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
    parser.add_argument("--confidence-threshold", type=float, default=0.5, help="Minimum confidence to accept classification, else classify as 'other'")
    args = parser.parse_args()

    posts = load_posts(args.input)
    if not isinstance(posts, list):
        raise RuntimeError("Unexpected posts data")

    # Always load existing labels — manual tags must never be overwritten
    existing_labels = load_existing_labels(args.csv) if os.path.exists(args.csv) else {}
    manual_labels = load_manual_labels(args.csv) if os.path.exists(args.csv) else []
    print(f"Loaded {len(existing_labels)} existing labels ({len(manual_labels)} manual)")

    # Model selection is automatic: fine-tuned on manual labels if any exist, zero-shot otherwise
    classifier = None
    if not args.skip_model:
        classifier = get_model(manual_labels=manual_labels if manual_labels else None)

    rows = []
    missed = 0
    total_images = sum(len(post.get("images", [])) for post in posts if isinstance(post.get("images"), list))

    start_time = time.time()
    print(f"Classifying {total_images} images...")

    progress_bar = tqdm(total=total_images, desc="Classifying images", unit="img") if tqdm else None

    for post in posts:
        post_id = str(post.get("post_id", "unknown"))
        image_urls = post.get("images", [])
        if not isinstance(image_urls, list):
            continue

        for i, img_url in enumerate(image_urls):
            image_id = f"{post_id}_{i}"
            local_path = os.path.join(IMAGES_DIR, f"{image_id}.jpg")

            if not os.path.exists(local_path):
                missed += 1
                if progress_bar:
                    progress_bar.update(1)
                continue

            existing = existing_labels.get(local_path)
            is_manual = bool(existing and existing["is_manual"])

            if is_manual:
                # Always preserve manual labels — never overwrite
                classification = {
                    "image_type": existing["type"],
                    "confidence": 1.0,
                    "reason": "manual override",
                    "model_source": "manual",
                }
            else:
                classification = classify_image(local_path, classifier)
                if classification["confidence"] < args.confidence_threshold:
                    classification["image_type"] = "other"
                    classification["reason"] = f"low confidence ({classification['confidence']:.2f}), {classification['reason']}"

            rows.append({
                "image_id": image_id,
                "post_id": post_id,
                "source_url": img_url,
                "local_path": local_path,
                "image_type": classification["image_type"],
                "confidence": classification["confidence"],
                "model_source": classification["model_source"],
                "reason": classification["reason"],
                "is_manual": is_manual,
            })

            if progress_bar:
                progress_bar.update(1)

    if progress_bar:
        progress_bar.close()

    duration = time.time() - start_time
    processed = len(rows)
    rate = processed / duration if duration > 0 else 0
    print(f"Done. Classified {processed} images, skipped {missed} missing in {duration:.2f}s ({rate:.1f} img/s)")

    write_json(args.output, rows)
    write_csv(args.csv, rows)
    write_report(args.report, rows)
    print(f"Wrote {args.output}, {args.csv}, {args.report}.")

    if args.preview > 0:
        print_preview(rows, args.preview)


if __name__ == "__main__":
    main()
