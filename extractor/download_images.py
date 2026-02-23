"""
Download images from previously extracted group posts.

Usage:
    python extractor/download_images.py

Expects:
    output/group_posts.json (created by extract_group.py)

Output:
    output/images/<post_id>_<index>.jpg
"""

import json
import os
import sys
import shutil

import requests

OUTPUT_DIR = "output"
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")
DOCS_IMAGE_DIR = os.path.join("docs", "images")
INPUT_FILE = os.path.join(OUTPUT_DIR, "group_posts.json")


def download_images():
    """Download all images referenced in group_posts.json."""

    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        print("Run extract_group.py first to extract posts.")
        sys.exit(1)

    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(DOCS_IMAGE_DIR, exist_ok=True)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support both envelope format and legacy flat array
    if isinstance(data, dict) and "posts" in data:
        posts = data["posts"]
    elif isinstance(data, list):
        posts = data
    else:
        print("Error: Unexpected JSON format in group_posts.json.")
        sys.exit(1)

    total = 0
    failed = 0

    for post in posts:
        post_id = post.get("post_id", "unknown")

        for j, img_url in enumerate(post.get("images", [])):
            if not img_url:
                continue

            filename = f"{post_id}_{j}.jpg"
            filepath = os.path.join(IMAGE_DIR, filename)
            docs_filepath = os.path.join(DOCS_IMAGE_DIR, filename)

            # skip if already downloaded (ensure both copies exist)
            if os.path.exists(filepath) or os.path.exists(docs_filepath):
                if os.path.exists(filepath) and not os.path.exists(docs_filepath):
                    shutil.copyfile(filepath, docs_filepath)
                elif os.path.exists(docs_filepath) and not os.path.exists(filepath):
                    shutil.copyfile(docs_filepath, filepath)
                print(f"  Skipped (exists): {filename}")
                continue

            try:
                resp = requests.get(img_url, timeout=30)
                resp.raise_for_status()
                with open(filepath, "wb") as img_file:
                    img_file.write(resp.content)
                shutil.copyfile(filepath, docs_filepath)
                print(f"  Saved: {filepath}")
                total += 1
            except Exception as e:
                print(f"  Failed (post {post_id}): {e}")
                failed += 1

    print(f"\nDone. Downloaded {total} images, {failed} failed.")


if __name__ == "__main__":
    download_images()
