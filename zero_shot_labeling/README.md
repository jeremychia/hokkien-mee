# Zero-shot labeling (local)

This folder contains a minimal, local zero-shot labeling pipeline using CLIP/OpenCLIP.

Quick steps (using `uv`):

1. Create or use a venv with uv (optional managed Python):

```bash
uv venv create .venv
uv venv use .venv
```

2. Install dependencies (two options):

- Using `uv` + pip interface:

```bash
uv pip install -r zero_shot_labeling/requirements.txt
```

- Or using `uv` project workflow (if you prefer `pyproject.toml` lock/sync):

```bash
uv add --lock
uv sync
```

3. Run a smoke test to check CUDA / Python environment:

```bash
python zero_shot_labeling/scripts/smoke_test.py
```

4. Run CLIP labeler (after deps installed):

```bash
python zero_shot_labeling/scripts/label_with_clip.py --images PATH/TO/IMAGES --labels zero_shot_labeling/data/labels.txt --out output.json --device cuda
```

Notes:
- The `label_with_clip.py` script will try to use the OpenAI `clip` package first. If you prefer `open-clip`, you can install `open-clip-torch` instead and edit the script to use it.
- For low-power machines, use smaller models (ViT-B/32) and `--device cpu` if GPU memory is insufficient.
