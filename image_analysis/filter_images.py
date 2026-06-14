"""
Filter image_labels.json to noodle images only and write absolute paths for
Label Studio import. Must be run from the repo root.
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter noodle images from image_labels.json for Label Studio import"
    )
    parser.add_argument("--labels", default="output/image_labels.json")
    parser.add_argument("--output", default="image_analysis/exports/noodle_paths.txt")
    args = parser.parse_args()

    labels_path = Path(args.labels)
    if not labels_path.exists():
        print(f"Error: {labels_path} not found. Run from repo root.", file=sys.stderr)
        sys.exit(1)

    with open(labels_path) as f:
        records = json.load(f)

    if not isinstance(records, list):
        print("Error: expected a JSON array in image_labels.json", file=sys.stderr)
        sys.exit(1)

    noodles = [r for r in records if r.get("image_type") == "noodles"]
    print(f"Total images: {len(records)}, noodle images: {len(noodles)}")

    written = []
    skipped = []
    for record in noodles:
        local_path = record.get("local_path", "")
        p = Path(local_path)
        abs_path = p if p.is_absolute() else p.resolve()
        if not abs_path.exists():
            skipped.append(str(abs_path))
            continue
        written.append(str(abs_path))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(written) + "\n")

    print(f"Written: {len(written)} paths → {output_path}")
    if skipped:
        print(f"Skipped (missing files): {len(skipped)}")
        for p in skipped[:5]:
            print(f"  {p}")
        if len(skipped) > 5:
            print(f"  ... and {len(skipped) - 5} more")


if __name__ == "__main__":
    main()
