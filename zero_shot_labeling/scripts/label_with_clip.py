#!/usr/bin/env python3
"""Simple CLIP-based zero-shot labeler.

Usage: python label_with_clip.py --images PATH --labels labels.txt --out out.json --device cuda

This script is intentionally small and robust: it first tries to import the OpenAI
`clip` binding (from the CLIP repo), and will raise a clear error if no model
backend is available.
"""
import argparse
import json
import math
import os
from pathlib import Path

from PIL import Image
import numpy as np

try:
    import clip
    import torch
except Exception as e:
    raise RuntimeError(
        "Please install dependencies first (see zero_shot_labeling/README.md).\n" + str(e)
    )


def load_labels(path):
    with open(path, "r", encoding="utf-8") as f:
        labels = [l.strip() for l in f.readlines() if l.strip()]
    return labels


def image_files_in(dirpath):
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    for p in Path(dirpath).rglob("*"):
        if p.suffix.lower() in exts:
            yield p


def topk(sim, labels, k=5):
    idx = np.argsort(-sim)[:k]
    return [(labels[i], float(sim[i])) for i in idx]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--images", required=True)
    p.add_argument("--labels", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--device", default="cuda")
    p.add_argument("--model", default="ViT-B/32")
    p.add_argument("--topk", type=int, default=5)
    args = p.parse_args()

    device = args.device if torch.cuda.is_available() or args.device == "cpu" else "cpu"
    device = torch.device(device)

    print("Loading model", args.model, "on", device)
    model, preprocess = clip.load(args.model, device=device)
    model.eval()

    labels = load_labels(args.labels)
    print(f"Loaded {len(labels)} labels")

    # build text embeddings
    with torch.no_grad():
        text_tokens = clip.tokenize(labels).to(device)
        text_feats = model.encode_text(text_tokens)
        text_feats = text_feats / text_feats.norm(dim=-1, keepdim=True)

    results = {}
    for img_path in image_files_in(args.images):
        try:
            img = preprocess(Image.open(img_path).convert("RGB")).unsqueeze(0).to(device)
            with torch.no_grad():
                img_feat = model.encode_image(img)
                img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
                sims = (img_feat @ text_feats.T).squeeze(0).cpu().numpy()

            entries = topk(sims, labels, k=args.topk)
            results[str(img_path)] = [{"label": l, "score": s} for l, s in entries]
            print(str(img_path), "=>", results[str(img_path)])
        except Exception as e:
            print("Failed on", img_path, e)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
